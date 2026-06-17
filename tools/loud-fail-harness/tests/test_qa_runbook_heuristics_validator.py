"""Contract-coverage matrix for qa_runbook_heuristics_validator (Story 19.1).

This docstring IS the contract-coverage checklist. Reviewers verify every row
maps to at least one passing test. Review-enforced, not CI-enforced (parallel to
the dependencies_validator matrix).

Fixture corpus (AC-6, non-vacuous):
    [x] valid fixture (3 project types + opt-out) → 0 findings   → test_valid_fixture_clean
    [x] AC-5(a) unknown heuristic name rejected                  → test_invalid_unknown_heuristic_name
    [x] AC-5(b) bad enablement value rejected                    → test_invalid_bad_enablement_value
    [x] AC-5(c) unknown project-type key rejected                → test_invalid_unknown_project_type
    [x] AC-5(d) out-of-set opt-out entry rejected                → test_invalid_opt_out_unknown_name

Pure-API shape rules:
    [x] absence of heuristics block is NOT a finding (FR42)      → test_absence_of_heuristics_block_is_clean
    [x] unrelated qa-runbook keys ignored                        → test_unrelated_keys_ignored
    [x] non-mapping heuristics block rejected                    → test_non_mapping_heuristics_block
    [x] non-mapping project-type entry rejected                  → test_non_mapping_project_type_entry
    [x] non-mapping story-level ac_map emits finding (not skip)  → test_non_mapping_ac_map_entry
    [x] non-list heuristic_opt_out rejected                      → test_non_list_opt_out
    [x] multiple findings reported (do not bail)                 → test_multiple_findings_reported
    [x] findings deterministic across invocations               → test_findings_deterministic
    [x] direct-API non-mapping top level → root finding          → test_validate_top_level_non_mapping

Input-hardening (Story 24.2 discipline):
    [x] HeuristicOptOutEntry hardens story_id (newline raises)   → test_opt_out_entry_hardens_story_id
    [x] HeuristicOptOutEntry hardens ac_key (whitespace raises)  → test_opt_out_entry_hardens_ac_key
    [x] hostile story-id key surfaces a finding (not a crash)    → test_hostile_opt_out_key_surfaces_finding
    [x] hostile story-id key produces exactly ONE finding (else:) → test_hostile_opt_out_key_produces_exactly_one_finding

CLI / main:
    [x] main() default-path (no args) validates template, exit 0 → test_main_no_args_validates_template
    [x] main() injected valid fixture exit 0 + OK                → test_main_injected_valid_exit_zero
    [x] main() injected invalid exit 1 + findings to stdout      → test_main_injected_invalid_exit_one
    [x] main() malformed YAML → exit 2 stderr                    → test_main_malformed_yaml_exit_two
    [x] main() unreadable file → exit 2 stderr                   → test_main_unreadable_exit_two
    [x] main() top-level non-mapping → exit 2 stderr             → test_main_top_level_non_mapping_exit_two
    [x] main() all-comments/empty (None) → exit 0                → test_main_all_comments_exit_zero

load helper:
    [x] returns parsed dict on valid                            → test_load_returns_dict
    [x] treats None (all-comments) as empty → returns {}         → test_load_treats_none_as_empty
    [x] raises RuntimeError on invalid shape                    → test_load_raises_on_invalid

Frozen-model + formatting:
    [x] ValidationFinding is frozen                             → test_validation_finding_frozen
    [x] format_findings renders pointer + remediation           → test_format_findings_renders
    [x] format_findings zero-findings renders OK                → test_format_findings_zero_ok

Contract test (AC-1 / AC-8 — reconciled at Story 19.2):
    [x] HeuristicKind == FROZEN_HEURISTIC_NAMES (== 7)          → test_contract_heuristic_kind_equals_frozen_seven

Landed invariants (AC-8 — the 19.1 seam guards, flipped by 19.2):
    [x] marker-taxonomy schema_version is "1.14"               → test_marker_taxonomy_version_is_1_14
    [x] heuristic-skipped sub_classifications are the 8-value set → test_heuristic_skipped_subclassifications_are_eight
    [x] HeuristicKind has exactly 7 values                     → test_heuristic_kind_has_seven_values
"""

from __future__ import annotations

import io
import pathlib
from contextlib import redirect_stderr, redirect_stdout
from typing import get_args

import pytest
import yaml
from pydantic import ValidationError

from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.qa_exploratory_heuristics import HeuristicKind
from loud_fail_harness.qa_runbook_heuristics_validator import (
    FROZEN_HEURISTIC_NAMES,
    HeuristicOptOutEntry,
    ValidationFinding,
    format_findings,
    load_qa_runbook_heuristics,
    main,
    validate_qa_runbook_heuristics,
)

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "qa-runbook-heuristics"
VALID = FIXTURES / "valid" / "qa-runbook.yaml"
INVALID = FIXTURES / "invalid"


def _load(path: pathlib.Path) -> dict:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


def _run_cli(path: pathlib.Path) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = main(["--qa-runbook-path", str(path)])
    return rc, out.getvalue(), err.getvalue()


# --------------------------------------------------------------------------- #
# Fixture corpus (AC-6)                                                        #
# --------------------------------------------------------------------------- #


def test_valid_fixture_clean() -> None:
    raw = _load(VALID)
    assert validate_qa_runbook_heuristics(raw, str(VALID)) == []


def test_invalid_unknown_heuristic_name() -> None:
    raw = _load(INVALID / "unknown-heuristic-name.yaml")
    findings = validate_qa_runbook_heuristics(raw, "f.yaml")
    assert any(
        f.pointer == "/heuristics/web/timing-attack-boundary"
        and "unknown heuristic name" in f.message
        for f in findings
    ), findings


def test_invalid_bad_enablement_value() -> None:
    raw = _load(INVALID / "bad-enablement-value.yaml")
    findings = validate_qa_runbook_heuristics(raw, "f.yaml")
    assert any(
        f.pointer == "/heuristics/api/empty-state"
        and "not in {enabled, disabled}" in f.message
        for f in findings
    ), findings


def test_invalid_unknown_project_type() -> None:
    raw = _load(INVALID / "unknown-project-type.yaml")
    findings = validate_qa_runbook_heuristics(raw, "f.yaml")
    assert any(
        f.pointer == "/heuristics/desktop"
        and "unknown project-type key" in f.message
        for f in findings
    ), findings


def test_invalid_opt_out_unknown_name() -> None:
    raw = _load(INVALID / "opt-out-unknown-name.yaml")
    findings = validate_qa_runbook_heuristics(raw, "f.yaml")
    assert any(
        f.pointer
        == "/behavioral_plan_overrides/auto-019-001/ac_1/heuristic_opt_out/0"
        and "not in FROZEN_HEURISTIC_NAMES" in f.message
        for f in findings
    ), findings


def test_invalid_flakiness_bad_knob() -> None:
    raw = _load(INVALID / "flakiness-bad-knob.yaml")
    findings = validate_qa_runbook_heuristics(raw, "f.yaml")
    assert any(
        f.pointer == "/flakiness/threshold_consecutive_runs"
        and "must be an int >= 1" in f.message
        for f in findings
    ), findings


# --------------------------------------------------------------------------- #
# Pure-API shape rules                                                         #
# --------------------------------------------------------------------------- #


def test_absence_of_heuristics_block_is_clean() -> None:
    assert validate_qa_runbook_heuristics({"masked_selectors": ["x"]}, "f") == []


def test_absence_of_flakiness_block_is_clean() -> None:
    # FR42: absence means "defaults apply", never a finding (Story 20.3).
    assert validate_qa_runbook_heuristics({"heuristics": {"web": {}}}, "f") == []


def test_valid_flakiness_block_clean() -> None:
    raw = {
        "flakiness": {
            "threshold_consecutive_runs": 5,
            "threshold_transient_fail_count": 2,
        }
    }
    assert validate_qa_runbook_heuristics(raw, "f") == []


def test_flakiness_partial_block_clean() -> None:
    # One knob present → the other defaults; no finding (absence = default).
    raw = {"flakiness": {"threshold_consecutive_runs": 3}}
    assert validate_qa_runbook_heuristics(raw, "f") == []


def test_flakiness_below_floor_rejected() -> None:
    findings = validate_qa_runbook_heuristics(
        {"flakiness": {"threshold_transient_fail_count": 0}}, "f"
    )
    assert any(
        f.pointer == "/flakiness/threshold_transient_fail_count"
        and "must be an int >= 1" in f.message
        for f in findings
    ), findings


def test_flakiness_non_int_knob_rejected() -> None:
    findings = validate_qa_runbook_heuristics(
        {"flakiness": {"threshold_consecutive_runs": "3"}}, "f"
    )
    assert any(
        f.pointer == "/flakiness/threshold_consecutive_runs"
        and "must be an int >= 1" in f.message
        for f in findings
    ), findings


def test_flakiness_bool_knob_rejected() -> None:
    # bool is an int subclass but not a valid threshold count — must be rejected.
    findings = validate_qa_runbook_heuristics(
        {"flakiness": {"threshold_transient_fail_count": True}}, "f"
    )
    assert any(
        f.pointer == "/flakiness/threshold_transient_fail_count"
        and "must be an int >= 1" in f.message
        for f in findings
    ), findings


def test_non_mapping_flakiness_block() -> None:
    findings = validate_qa_runbook_heuristics({"flakiness": [1, 2]}, "f")
    assert any(
        f.pointer == "/flakiness" and "must be a mapping" in f.message
        for f in findings
    ), findings


def test_unrelated_keys_ignored() -> None:
    raw = {
        "mobile_app_package_name": "com.example.app",
        "tier_3_semantic_verification": {"provider": "x"},
        "heuristics": {"web": {"empty-state": "enabled"}},
    }
    assert validate_qa_runbook_heuristics(raw, "f") == []


def test_non_mapping_heuristics_block() -> None:
    findings = validate_qa_runbook_heuristics({"heuristics": ["not", "a", "map"]}, "f")
    assert any(
        f.pointer == "/heuristics" and "must be a mapping" in f.message
        for f in findings
    ), findings


def test_non_mapping_project_type_entry() -> None:
    findings = validate_qa_runbook_heuristics(
        {"heuristics": {"web": "not-a-mapping"}}, "f"
    )
    assert any(
        f.pointer == "/heuristics/web" and "must be a mapping" in f.message
        for f in findings
    ), findings


def test_non_mapping_ac_map_entry() -> None:
    raw = {
        "behavioral_plan_overrides": {
            "auto-019-001": ["not", "a", "mapping"]
        }
    }
    findings = validate_qa_runbook_heuristics(raw, "f")
    assert any(
        f.pointer == "/behavioral_plan_overrides/auto-019-001"
        and "must be a mapping" in f.message
        for f in findings
    ), findings


def test_non_list_opt_out() -> None:
    raw = {
        "behavioral_plan_overrides": {
            "auto-019-001": {"ac_1": {"heuristic_opt_out": "empty-state"}}
        }
    }
    findings = validate_qa_runbook_heuristics(raw, "f")
    assert any(
        f.pointer.endswith("/heuristic_opt_out")
        and "must be a sequence" in f.message
        for f in findings
    ), findings


def test_multiple_findings_reported() -> None:
    raw = {
        "heuristics": {
            "web": {"bogus-heuristic": "enabled"},
            "desktop": {"empty-state": "enabled"},
        }
    }
    findings = validate_qa_runbook_heuristics(raw, "f")
    pointers = {f.pointer for f in findings}
    assert "/heuristics/web/bogus-heuristic" in pointers
    assert "/heuristics/desktop" in pointers


def test_findings_deterministic() -> None:
    raw = {
        "heuristics": {
            "web": {"bogus": "enabled", "empty-state": "maybe"},
            "zzz": {"empty-state": "enabled"},
        }
    }
    f1 = validate_qa_runbook_heuristics(raw, "f")
    f2 = validate_qa_runbook_heuristics(raw, "f")
    assert [(f.pointer, f.message, f.remediation) for f in f1] == [
        (f.pointer, f.message, f.remediation) for f in f2
    ]


def test_validate_top_level_non_mapping() -> None:
    findings = validate_qa_runbook_heuristics("not a dict", "f")  # type: ignore[arg-type]
    assert len(findings) == 1
    assert findings[0].pointer == "<root>"
    assert "top-level must be a YAML mapping" in findings[0].message


# --------------------------------------------------------------------------- #
# Input-hardening (Story 24.2 discipline)                                      #
# --------------------------------------------------------------------------- #


def test_opt_out_entry_hardens_story_id() -> None:
    with pytest.raises(ValidationError):
        HeuristicOptOutEntry(story_id="auto-019\n001", ac_key="ac_1")


def test_opt_out_entry_hardens_ac_key() -> None:
    with pytest.raises(ValidationError):
        HeuristicOptOutEntry(story_id="auto-019-001", ac_key="   ")


def test_hostile_opt_out_key_surfaces_finding() -> None:
    raw = {
        "behavioral_plan_overrides": {
            "auto-019\n001": {"ac_1": {"heuristic_opt_out": ["empty-state"]}}
        }
    }
    findings = validate_qa_runbook_heuristics(raw, "f")
    assert any("hostile input in opt-out key path" in f.message for f in findings), findings


def test_hostile_opt_out_key_produces_exactly_one_finding() -> None:
    """Verify the else: fix — _validate_opt_out_list must NOT run after ValidationError."""
    raw = {
        "behavioral_plan_overrides": {
            "auto-019\n001": {"ac_1": {"heuristic_opt_out": ["empty-state"]}}
        }
    }
    findings = validate_qa_runbook_heuristics(raw, "f")
    assert len(findings) == 1, f"expected 1 finding, got {len(findings)}: {findings}"
    assert "hostile input in opt-out key path" in findings[0].message


# --------------------------------------------------------------------------- #
# CLI / main                                                                   #
# --------------------------------------------------------------------------- #


def test_main_no_args_validates_template() -> None:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = main([])
    assert rc == 0, f"stdout={out.getvalue()!r} stderr={err.getvalue()!r}"
    assert "OK: 0 findings." in out.getvalue()


def test_main_injected_valid_exit_zero() -> None:
    rc, out, err = _run_cli(VALID)
    assert rc == 0, f"out={out!r} err={err!r}"
    assert "OK: 0 findings." in out


def test_main_injected_invalid_exit_one() -> None:
    rc, out, err = _run_cli(INVALID / "unknown-heuristic-name.yaml")
    assert rc == 1
    assert "ERROR:" in out
    assert "timing-attack-boundary" in out
    assert err == ""


def test_main_malformed_yaml_exit_two(tmp_path: pathlib.Path) -> None:
    p = tmp_path / "qa-runbook.yaml"
    p.write_text("foo: bar:\n  - [unclosed\n", encoding="utf-8")
    rc, _, err = _run_cli(p)
    assert rc == 2
    assert "harness-level error" in err
    assert "YAML parse failure" in err


def test_main_unreadable_exit_two(tmp_path: pathlib.Path) -> None:
    rc, _, err = _run_cli(tmp_path / "absent.yaml")
    assert rc == 2
    assert "unreadable" in err


def test_main_top_level_non_mapping_exit_two(tmp_path: pathlib.Path) -> None:
    p = tmp_path / "qa-runbook.yaml"
    p.write_text("- a\n- b\n", encoding="utf-8")
    rc, _, err = _run_cli(p)
    assert rc == 2
    assert "did not parse to a YAML mapping" in err


def test_main_all_comments_exit_zero(tmp_path: pathlib.Path) -> None:
    p = tmp_path / "qa-runbook.yaml"
    p.write_text("# only comments\n# nothing active\n", encoding="utf-8")
    rc, out, _ = _run_cli(p)
    assert rc == 0
    assert "OK: 0 findings." in out


# --------------------------------------------------------------------------- #
# load helper                                                                  #
# --------------------------------------------------------------------------- #


def test_load_returns_dict() -> None:
    raw = load_qa_runbook_heuristics(VALID)
    assert isinstance(raw, dict)
    assert raw["heuristics"]["mobile"]["rate-limit-boundary"] == "disabled"


def test_load_treats_none_as_empty(tmp_path: pathlib.Path) -> None:
    p = tmp_path / "qa-runbook.yaml"
    p.write_text("# all comments\n", encoding="utf-8")
    assert load_qa_runbook_heuristics(p) == {}


def test_load_raises_on_invalid() -> None:
    with pytest.raises(RuntimeError) as exc:
        load_qa_runbook_heuristics(INVALID / "unknown-heuristic-name.yaml")
    assert "failed heuristics shape validation" in str(exc.value)


# --------------------------------------------------------------------------- #
# Frozen-model + formatting                                                    #
# --------------------------------------------------------------------------- #


def test_validation_finding_frozen() -> None:
    f = ValidationFinding(pointer="/x", message="m", remediation="r")
    with pytest.raises(ValidationError):
        f.message = "other"  # type: ignore[misc]


def test_format_findings_renders() -> None:
    f = ValidationFinding(
        pointer="/heuristics/web/bogus",
        message="unknown heuristic name 'bogus'",
        remediation="(per ADR-010 / FR-P2-5)",
    )
    rendered = format_findings([f], "qa-runbook.yaml")
    assert "qa-runbook heuristics validation (ADR-010 / FR-P2-5): qa-runbook.yaml" in rendered
    assert "ERROR: 1 shape-rule violation(s)." in rendered
    assert "/heuristics/web/bogus" in rendered
    assert "(per ADR-010 / FR-P2-5)" in rendered


def test_format_findings_zero_ok() -> None:
    rendered = format_findings([], "qa-runbook.yaml")
    assert "OK: 0 findings." in rendered
    assert "ERROR" not in rendered


# --------------------------------------------------------------------------- #
# Contract test (AC-1 / AC-8 — reconciled at Story 19.2)                       #
# --------------------------------------------------------------------------- #


def test_contract_heuristic_kind_equals_frozen_seven() -> None:
    """Story 19.2 reconciled the seam: ``HeuristicKind`` now EQUALS the frozen
    7-set (was a strict subset at 19.1). The subset assertion still holds (now
    satisfied BY equality); the equality assertion is the new invariant tying
    the driving Literal to the single source of truth."""
    assert set(get_args(HeuristicKind)).issubset(FROZEN_HEURISTIC_NAMES)
    assert set(get_args(HeuristicKind)) == FROZEN_HEURISTIC_NAMES
    assert len(FROZEN_HEURISTIC_NAMES) == 7
    # The four ADR-010 additions are now present in the driving Literal too.
    assert {
        "rate-limit-boundary",
        "locale-i18n-edge",
        "large-input-boundary",
        "permission-boundary",
    }.issubset(set(get_args(HeuristicKind)))


# --------------------------------------------------------------------------- #
# Landed invariants (AC-8) — the 19.1 seam guards, flipped by Story 19.2       #
# --------------------------------------------------------------------------- #


def _marker_taxonomy() -> dict:
    path = find_repo_root() / "schemas" / "marker-taxonomy.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


def test_marker_taxonomy_version_is_1_14() -> None:
    assert _marker_taxonomy()["schema_version"] == "1.19"


def test_heuristic_skipped_subclassifications_are_eight() -> None:
    markers = _marker_taxonomy()["markers"]
    heuristic_skipped = next(
        m for m in markers if m["marker_class"] == "heuristic-skipped"
    )
    assert heuristic_skipped["sub_classifications"] == [
        "empty-state",
        "error-state",
        "auth-boundary",
        "rate-limit-boundary",
        "locale-i18n-edge",
        "large-input-boundary",
        "permission-boundary",
        "flow-branch",
    ]


def test_heuristic_kind_has_seven_values() -> None:
    assert len(get_args(HeuristicKind)) == 7
    assert set(get_args(HeuristicKind)) == FROZEN_HEURISTIC_NAMES
