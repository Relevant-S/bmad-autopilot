"""Contract-coverage matrix for the dependencies_validator (SDN-001 shape).

This docstring IS the contract-coverage checklist required by AC-6. Reviewers
verify every row maps to at least one passing test in this module. The matrix
is review-enforced, NOT CI-enforced (parallel to story 1.2 / 1.3 / 1.4 / 1.5).

Pure-API positive cases (AC-6 cases 2-8):
    [x] total-block profile validates                            → test_total_block_profile_validates
    [x] graceful-degrade profile validates                       → test_graceful_degrade_profile_validates
    [x] opt-in-skip profile validates (silent path)              → test_opt_in_skip_profile_validates_silent
    [x] opt-in-skip profile validates (sub_classifications path) → test_opt_in_skip_profile_validates_with_sub_classifications
    [x] per-lifecycle-phase variance supported                   → test_per_lifecycle_phase_variance_supported
    [x] by_project_type shape supported                          → test_by_project_type_supported
    [x] phase field optional (absent + "1.5")                    → test_phase_field_optional

Pure-API negative cases (AC-6 cases 9-19):
    [x] unknown failure_profile value rejected                   → test_unknown_failure_profile_value_rejected
    [x] missing required diagnostic on total-block (init phase)  → test_missing_required_field_total_block_init_rejected
    [x] runtime total-block without diagnostic IS valid          → test_runtime_total_block_without_diagnostic_valid
    [x] missing required fields on graceful-degrade (both)       → test_missing_required_fields_graceful_degrade_rejected
    [x] profiles and by_project_type mutually exclusive          → test_profiles_and_by_project_type_mutually_exclusive
    [x] neither profiles nor by_project_type rejected            → test_neither_profiles_nor_by_project_type_rejected
    [x] unknown lifecycle phase rejected                         → test_unknown_lifecycle_phase_rejected
    [x] unknown project type rejected                            → test_unknown_project_type_rejected
    [x] unknown top-level key rejected                           → test_unknown_top_level_key_rejected
    [x] missing top-level schema_version rejected                → test_missing_schema_version_rejected
    [x] missing top-level dependencies rejected                  → test_missing_dependencies_rejected
    [x] sub_classifications emits_marker only valid              → test_sub_classifications_emits_marker_only_valid
    [x] sub_classifications emits_marker + diagnostic_pointer valid → test_opt_in_skip_profile_validates_with_sub_classifications
    [x] sub_classifications silent: true only valid              → test_sub_classifications_silent_only_valid
    [x] sub_classifications both emits + silent rejected         → test_sub_classifications_both_emits_and_silent_rejected
    [x] sub_classifications neither emits nor silent rejected    → test_sub_classifications_neither_emits_nor_silent_rejected
    [x] sub_classifications missing condition rejected           → test_sub_classifications_missing_condition_rejected
    [x] sub_classifications unknown field rejected               → test_sub_classifications_unknown_field_rejected
    [x] unknown field on profile spec rejected                   → test_unknown_field_on_profile_spec_rejected
    [x] unknown field on dependency entry rejected               → test_unknown_field_on_dependency_entry_rejected
    [x] non-dict dependency entry rejected                       → test_non_dict_dependency_entry_rejected

Multiple findings + determinism (AC-6 cases 17, 19):
    [x] multiple findings reported (do not bail after first)     → test_multiple_findings_reported
    [x] findings deterministic across two invocations            → test_findings_deterministic

CLI / integration (AC-6 cases 1, 20-22):
    [x] canonical schema validates (exit 0, no findings)         → test_canonical_schema_validates
    [x] main() default-path resolution (no args)                 → test_main_with_no_flags_resolves_canonical_schema
    [x] loud-fail on malformed YAML (exit 2, stderr)             → test_loud_fail_on_malformed_yaml
    [x] loud-fail on file unreadable (exit 2, stderr)            → test_loud_fail_on_file_unreadable
    [x] loud-fail on top-level non-mapping (exit 2, stderr)      → test_loud_fail_on_top_level_non_mapping
    [x] main() exits 1 on validation findings                    → test_main_exits_one_on_validation_finding
    [x] main() prints findings to stdout (not stderr)            → test_main_prints_findings_to_stdout

Cross-story seam (AC-5 + AC-6 case 23):
    [x] enumeration_check picks up dependencies.yaml             → test_enumeration_check_picks_up_dependencies_yaml

Pydantic v2 frozen-model discipline:
    [x] ValidationFinding is frozen (assignment raises)          → test_validation_finding_is_frozen

NFR-O5 named-invariant diagnostic shape:
    [x] finding shape carries pointer + message + remediation    → test_finding_message_names_pointer_invariant_remediation
    [x] format_findings renders pointer + message + remediation  → test_format_findings_renders_pointer_and_remediation

load_dependencies helper (AC-2 surface):
    [x] returns parsed dict on valid file                        → test_load_dependencies_returns_dict
    [x] raises RuntimeError on invalid shape                     → test_load_dependencies_raises_on_invalid_shape
    [x] raises RuntimeError on top-level non-mapping             → test_load_dependencies_raises_on_top_level_non_mapping

Coverage (AC-6):
    [x] dependencies_validator.py module-level statement coverage ≥ 90% → review-enforced; not a CI gate
"""

from __future__ import annotations

import io
import pathlib
from contextlib import redirect_stderr, redirect_stdout

import pytest
import yaml
from pydantic import ValidationError

from loud_fail_harness import enumeration_check
from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.dependencies_validator import (
    ValidationFinding,
    format_findings,
    load_dependencies,
    main,
    validate_dependencies,
)


REPO_ROOT = find_repo_root()
CANONICAL_DEPENDENCIES_PATH = REPO_ROOT / "schemas" / "dependencies.yaml"


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _write_yaml(path: pathlib.Path, data: object) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _wrap_top_level(deps: dict, schema_version: str = "1.0") -> dict:
    """Build a minimal SDN-001 top-level wrapper around a dependencies dict."""
    return {"schema_version": schema_version, "dependencies": deps}


def _run_cli(deps_path: pathlib.Path) -> tuple[int, str, str]:
    """Invoke main() with the test-injection flag; capture streams."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = main(["--dependencies-path", str(deps_path)])
    return rc, out.getvalue(), err.getvalue()


# --------------------------------------------------------------------------- #
# Pure-API positive cases                                                     #
# --------------------------------------------------------------------------- #


def test_total_block_profile_validates() -> None:
    """Synthetic claude-code-shaped fixture: init total-block + diagnostic;
    runtime total-block (no diagnostic, mirroring SDN-001's canonical pattern
    for claude-code / bmad-core / tea-module)."""
    raw = _wrap_top_level(
        {
            "synth-tool": {
                "version_floor": "1.0",
                "profiles": {
                    "init": {
                        "profile": "total-block",
                        "diagnostic": "Synth tool v1.0+ required.",
                    },
                    "runtime": {"profile": "total-block"},
                },
            }
        }
    )
    assert validate_dependencies(raw, "synthetic.yaml") == []


def test_graceful_degrade_profile_validates() -> None:
    """Synthetic playwright-mcp-runtime-shaped fixture."""
    raw = _wrap_top_level(
        {
            "synth-mcp": {
                "by_project_type": {
                    "web": {
                        "profiles": {
                            "init": {
                                "profile": "total-block",
                                "diagnostic": "Synth MCP unreachable.",
                            },
                            "runtime": {
                                "profile": "graceful-degrade",
                                "marker_class": "env-setup-failed",
                                "diagnostic_pointer": "Synth MCP unavailable mid-run.",
                            },
                        }
                    }
                }
            }
        }
    )
    assert validate_dependencies(raw, "synthetic.yaml") == []


def test_opt_in_skip_profile_validates_silent() -> None:
    """opt-in-skip with no sub_classifications — fully silent."""
    raw = _wrap_top_level(
        {
            "synth-opt": {
                "profiles": {
                    "init": {"profile": "opt-in-skip"},
                    "runtime": {"profile": "opt-in-skip"},
                }
            }
        }
    )
    assert validate_dependencies(raw, "synthetic.yaml") == []


def test_opt_in_skip_profile_validates_with_sub_classifications() -> None:
    """LAD-shaped synthetic: opt-in-skip + sub_classifications with one
    emits_marker entry + one silent entry."""
    raw = _wrap_top_level(
        {
            "synth-lad": {
                "profiles": {
                    "init": {
                        "profile": "opt-in-skip",
                        "sub_classifications": [
                            {
                                "condition": "configured-but-api-key-missing",
                                "emits_marker": "LAD-skipped",
                                "diagnostic_pointer": "Set the API key.",
                            },
                            {"condition": "unconfigured", "silent": True},
                        ],
                    },
                    "runtime": {"profile": "opt-in-skip"},
                }
            }
        }
    )
    assert validate_dependencies(raw, "synthetic.yaml") == []


def test_per_lifecycle_phase_variance_supported() -> None:
    """init: total-block + runtime: graceful-degrade is the SDN-001 invariant
    PRD line 528 names. The validator MUST NOT enforce phase-uniformity."""
    raw = _wrap_top_level(
        {
            "synth-mcp": {
                "by_project_type": {
                    "web": {
                        "profiles": {
                            "init": {
                                "profile": "total-block",
                                "diagnostic": "Required at init.",
                            },
                            "runtime": {
                                "profile": "graceful-degrade",
                                "marker_class": "env-setup-failed",
                                "diagnostic_pointer": "Skipped at runtime.",
                            },
                        }
                    }
                }
            }
        }
    )
    findings = validate_dependencies(raw, "synthetic.yaml")
    assert findings == [], (
        "phase-uniformity must NOT be enforced — init/runtime asymmetry IS the design"
    )


def test_by_project_type_supported() -> None:
    """All three project-type keys (web, api, mobile) accepted."""
    raw = _wrap_top_level(
        {
            "synth-mcp": {
                "by_project_type": {
                    "web": {
                        "profiles": {
                            "init": {"profile": "opt-in-skip"},
                            "runtime": {"profile": "opt-in-skip"},
                        }
                    },
                    "api": {
                        "profiles": {
                            "init": {"profile": "opt-in-skip"},
                            "runtime": {"profile": "opt-in-skip"},
                        }
                    },
                    "mobile": {
                        "profiles": {
                            "init": {"profile": "opt-in-skip"},
                            "runtime": {"profile": "opt-in-skip"},
                        }
                    },
                }
            }
        }
    )
    assert validate_dependencies(raw, "synthetic.yaml") == []


def test_phase_field_optional() -> None:
    raw_no_phase = _wrap_top_level(
        {
            "synth-mvp": {
                "profiles": {"init": {"profile": "opt-in-skip"}, "runtime": {"profile": "opt-in-skip"}},
            }
        }
    )
    assert validate_dependencies(raw_no_phase, "synthetic.yaml") == []

    raw_with_phase = _wrap_top_level(
        {
            "synth-1-5": {
                "phase": "1.5",
                "profiles": {"init": {"profile": "opt-in-skip"}, "runtime": {"profile": "opt-in-skip"}},
            }
        }
    )
    assert validate_dependencies(raw_with_phase, "synthetic.yaml") == []


# --------------------------------------------------------------------------- #
# Pure-API negative cases                                                     #
# --------------------------------------------------------------------------- #


def test_unknown_failure_profile_value_rejected() -> None:
    raw = _wrap_top_level(
        {
            "synth-bogus": {
                "profiles": {
                    "init": {"profile": "bogus-value"},
                    "runtime": {"profile": "opt-in-skip"},
                }
            }
        }
    )
    findings = validate_dependencies(raw, "synthetic.yaml")
    assert any(
        "bogus-value" in f.message
        and f.pointer == "/dependencies/synth-bogus/profiles/init/profile"
        for f in findings
    ), findings


def test_missing_required_field_total_block_init_rejected() -> None:
    raw = _wrap_top_level(
        {
            "synth-init": {
                "profiles": {"init": {"profile": "total-block"}},
            }
        }
    )
    findings = validate_dependencies(raw, "synthetic.yaml")
    assert any(
        f.pointer == "/dependencies/synth-init/profiles/init/diagnostic"
        and "missing required field 'diagnostic' for total-block profile" in f.message
        and "(per SDN-001" in f.remediation
        for f in findings
    ), findings


def test_runtime_total_block_without_diagnostic_valid() -> None:
    """Per SDN-001 lines 624-730: runtime total-block on claude-code /
    bmad-core / tea-module declares NO diagnostic (the precondition surface
    is init; runtime total-block emits via run-state preservation marker)."""
    raw = _wrap_top_level(
        {
            "synth-runtime": {
                "profiles": {
                    "init": {"profile": "total-block", "diagnostic": "x"},
                    "runtime": {"profile": "total-block"},
                }
            }
        }
    )
    assert validate_dependencies(raw, "synthetic.yaml") == []


def test_missing_required_fields_graceful_degrade_rejected() -> None:
    """Both marker_class AND diagnostic_pointer missing → TWO findings
    (proves AC-2's "do not bail after first" rule)."""
    raw = _wrap_top_level(
        {
            "synth-gd": {
                "profiles": {
                    "runtime": {"profile": "graceful-degrade"},
                }
            }
        }
    )
    findings = validate_dependencies(raw, "synthetic.yaml")
    pointers = {f.pointer for f in findings}
    assert "/dependencies/synth-gd/profiles/runtime/marker_class" in pointers
    assert "/dependencies/synth-gd/profiles/runtime/diagnostic_pointer" in pointers


def test_profiles_and_by_project_type_mutually_exclusive() -> None:
    raw = _wrap_top_level(
        {
            "synth-both": {
                "profiles": {"init": {"profile": "opt-in-skip"}},
                "by_project_type": {
                    "web": {"profiles": {"init": {"profile": "opt-in-skip"}}}
                },
            }
        }
    )
    findings = validate_dependencies(raw, "synthetic.yaml")
    assert any(
        "both present" in f.message and f.pointer == "/dependencies/synth-both"
        for f in findings
    ), findings


def test_neither_profiles_nor_by_project_type_rejected() -> None:
    raw = _wrap_top_level({"synth-neither": {"version_floor": "1.0"}})
    findings = validate_dependencies(raw, "synthetic.yaml")
    assert any(
        "neither present" in f.message and f.pointer == "/dependencies/synth-neither"
        for f in findings
    ), findings


def test_unknown_lifecycle_phase_rejected() -> None:
    raw = _wrap_top_level(
        {
            "synth-bad-phase": {
                "profiles": {
                    "init": {"profile": "opt-in-skip"},
                    "staging": {"profile": "opt-in-skip"},
                }
            }
        }
    )
    findings = validate_dependencies(raw, "synthetic.yaml")
    assert any(
        f.pointer == "/dependencies/synth-bad-phase/profiles/staging"
        and "staging" in f.message
        and "init, runtime" in f.message
        for f in findings
    ), findings


def test_unknown_project_type_rejected() -> None:
    raw = _wrap_top_level(
        {
            "synth-bad-pt": {
                "by_project_type": {
                    "desktop": {"profiles": {"init": {"profile": "opt-in-skip"}}}
                }
            }
        }
    )
    findings = validate_dependencies(raw, "synthetic.yaml")
    assert any(
        f.pointer == "/dependencies/synth-bad-pt/by_project_type/desktop"
        and "desktop" in f.message
        for f in findings
    ), findings


def test_unknown_top_level_key_rejected() -> None:
    raw = {
        "schema_version": "1.0",
        "dependencies": {},
        "foo": "bar",
    }
    findings = validate_dependencies(raw, "synthetic.yaml")
    assert any(
        f.pointer == "/foo" and "unknown top-level key 'foo'" in f.message
        for f in findings
    ), findings


def test_missing_schema_version_rejected() -> None:
    raw = {"dependencies": {}}
    findings = validate_dependencies(raw, "synthetic.yaml")
    assert any(
        f.pointer == "/schema_version"
        and "missing required field 'schema_version'" in f.message
        for f in findings
    ), findings


def test_missing_dependencies_rejected() -> None:
    raw = {"schema_version": "1.0"}
    findings = validate_dependencies(raw, "synthetic.yaml")
    assert any(
        f.pointer == "/dependencies"
        and "missing required field 'dependencies'" in f.message
        for f in findings
    ), findings


def test_sub_classifications_emits_marker_only_valid() -> None:
    raw = _wrap_top_level(
        {
            "synth-sc": {
                "profiles": {
                    "init": {
                        "profile": "opt-in-skip",
                        "sub_classifications": [
                            {"condition": "x", "emits_marker": "y"}
                        ],
                    }
                }
            }
        }
    )
    assert validate_dependencies(raw, "synthetic.yaml") == []


def test_sub_classifications_silent_only_valid() -> None:
    raw = _wrap_top_level(
        {
            "synth-sc": {
                "profiles": {
                    "init": {
                        "profile": "opt-in-skip",
                        "sub_classifications": [
                            {"condition": "x", "silent": True}
                        ],
                    }
                }
            }
        }
    )
    assert validate_dependencies(raw, "synthetic.yaml") == []


def test_sub_classifications_both_emits_and_silent_rejected() -> None:
    raw = _wrap_top_level(
        {
            "synth-sc": {
                "profiles": {
                    "init": {
                        "profile": "opt-in-skip",
                        "sub_classifications": [
                            {"condition": "x", "emits_marker": "y", "silent": True}
                        ],
                    }
                }
            }
        }
    )
    findings = validate_dependencies(raw, "synthetic.yaml")
    assert any(
        "both present" in f.message
        and f.pointer == "/dependencies/synth-sc/profiles/init/sub_classifications/0"
        for f in findings
    ), findings


def test_sub_classifications_neither_emits_nor_silent_rejected() -> None:
    raw = _wrap_top_level(
        {
            "synth-sc": {
                "profiles": {
                    "init": {
                        "profile": "opt-in-skip",
                        "sub_classifications": [{"condition": "x"}],
                    }
                }
            }
        }
    )
    findings = validate_dependencies(raw, "synthetic.yaml")
    assert any(
        "neither present" in f.message
        and f.pointer == "/dependencies/synth-sc/profiles/init/sub_classifications/0"
        for f in findings
    ), findings


def test_sub_classifications_missing_condition_rejected() -> None:
    raw = _wrap_top_level(
        {
            "synth-sc": {
                "profiles": {
                    "init": {
                        "profile": "opt-in-skip",
                        "sub_classifications": [{"emits_marker": "y"}],
                    }
                }
            }
        }
    )
    findings = validate_dependencies(raw, "synthetic.yaml")
    assert any(
        "missing required field 'condition'" in f.message
        and f.pointer
        == "/dependencies/synth-sc/profiles/init/sub_classifications/0/condition"
        for f in findings
    ), findings


def test_sub_classifications_unknown_field_rejected() -> None:
    raw = _wrap_top_level(
        {
            "synth-sc": {
                "profiles": {
                    "init": {
                        "profile": "opt-in-skip",
                        "sub_classifications": [
                            {
                                "condition": "x",
                                "emits_marker": "y",
                                "extra_field": "bad",
                            }
                        ],
                    }
                }
            }
        }
    )
    findings = validate_dependencies(raw, "synthetic.yaml")
    assert any(
        "unknown field 'extra_field'" in f.message
        and f.pointer.endswith("/sub_classifications/0/extra_field")
        for f in findings
    ), findings


def test_unknown_field_on_profile_spec_rejected() -> None:
    raw = _wrap_top_level(
        {
            "synth-bad-spec": {
                "profiles": {
                    "init": {"profile": "opt-in-skip", "rogue_field": "x"}
                }
            }
        }
    )
    findings = validate_dependencies(raw, "synthetic.yaml")
    assert any(
        f.pointer == "/dependencies/synth-bad-spec/profiles/init/rogue_field"
        and "unknown field 'rogue_field'" in f.message
        for f in findings
    ), findings


def test_unknown_field_on_dependency_entry_rejected() -> None:
    raw = _wrap_top_level(
        {
            "synth-bad-dep": {
                "rogue_top": "x",
                "profiles": {"init": {"profile": "opt-in-skip"}},
            }
        }
    )
    findings = validate_dependencies(raw, "synthetic.yaml")
    assert any(
        f.pointer == "/dependencies/synth-bad-dep/rogue_top"
        and "unknown field 'rogue_top'" in f.message
        for f in findings
    ), findings


def test_non_dict_dependency_entry_rejected() -> None:
    raw = _wrap_top_level({"synth-list": ["not", "a", "mapping"]})
    findings = validate_dependencies(raw, "synthetic.yaml")
    assert any(
        f.pointer == "/dependencies/synth-list"
        and "must be a mapping" in f.message
        for f in findings
    ), findings


# --------------------------------------------------------------------------- #
# Multiple findings + determinism                                             #
# --------------------------------------------------------------------------- #


def test_multiple_findings_reported() -> None:
    """TWO independent shape violations on different deps → BOTH reported.

    Proves AC-2 / AC-6's "do not bail after first" rule.
    """
    raw = _wrap_top_level(
        {
            "dep-a": {
                "profiles": {
                    "init": {"profile": "bogus-a"},
                }
            },
            "dep-b": {
                "profiles": {
                    "init": {"profile": "graceful-degrade"},  # missing both fields
                }
            },
        }
    )
    findings = validate_dependencies(raw, "synthetic.yaml")
    pointers = {f.pointer for f in findings}
    assert "/dependencies/dep-a/profiles/init/profile" in pointers
    assert "/dependencies/dep-b/profiles/init/marker_class" in pointers
    assert "/dependencies/dep-b/profiles/init/diagnostic_pointer" in pointers


def test_findings_deterministic() -> None:
    """validate_dependencies twice on the same input yields byte-identical
    finding lists (parallel to 1.5's test_orphan_ordering_deterministic)."""
    raw = _wrap_top_level(
        {
            "dep-a": {
                "profiles": {
                    "init": {"profile": "bogus-a"},
                    "runtime": {"profile": "graceful-degrade"},
                }
            },
            "dep-b": {
                "profiles": {
                    "init": {"profile": "total-block"},  # missing diagnostic
                }
            },
            "dep-c": {"version_floor": "1.0"},  # neither profiles nor by_project_type
        }
    )
    f1 = validate_dependencies(raw, "synthetic.yaml")
    f2 = validate_dependencies(raw, "synthetic.yaml")
    assert [(f.pointer, f.message, f.remediation) for f in f1] == [
        (f.pointer, f.message, f.remediation) for f in f2
    ]
    # And the dump is byte-identical:
    assert [f.model_dump_json() for f in f1] == [f.model_dump_json() for f in f2]


# --------------------------------------------------------------------------- #
# CLI / integration                                                           #
# --------------------------------------------------------------------------- #


def test_canonical_schema_validates() -> None:
    """The on-disk schemas/dependencies.yaml landed by AC-1 passes its own
    validator (exit 0, no findings)."""
    rc, out, err = _run_cli(CANONICAL_DEPENDENCIES_PATH)
    assert rc == 0, f"canonical schema failed validation: stdout={out!r} stderr={err!r}"
    assert "OK: 0 findings." in out
    assert "ERROR" not in out


def test_main_with_no_flags_resolves_canonical_schema() -> None:
    """No CLI flags → main() resolves schemas/dependencies.yaml via
    find_repo_root. Mirrors the canonical CI invocation."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = main([])
    assert rc == 0
    assert "OK: 0 findings." in out.getvalue()


def test_loud_fail_on_malformed_yaml(tmp_path: pathlib.Path) -> None:
    deps_path = tmp_path / "dependencies.yaml"
    deps_path.write_text("foo: bar:\n  - [unclosed\n", encoding="utf-8")
    rc, _, err = _run_cli(deps_path)
    assert rc == 2
    assert "harness-level error" in err
    assert "YAML parse failure" in err
    assert str(deps_path) in err


def test_loud_fail_on_file_unreadable(tmp_path: pathlib.Path) -> None:
    nonexistent = tmp_path / "definitely-absent-1-6.yaml"
    rc, _, err = _run_cli(nonexistent)
    assert rc == 2
    assert "harness-level error" in err
    assert "unreadable" in err
    assert str(nonexistent) in err


def test_loud_fail_on_top_level_non_mapping(tmp_path: pathlib.Path) -> None:
    deps_path = tmp_path / "dependencies.yaml"
    deps_path.write_text("- item-a\n- item-b\n", encoding="utf-8")
    rc, _, err = _run_cli(deps_path)
    assert rc == 2
    assert "did not parse to a YAML mapping" in err
    assert str(deps_path) in err


def test_main_exits_one_on_validation_finding(tmp_path: pathlib.Path) -> None:
    deps_path = tmp_path / "dependencies.yaml"
    _write_yaml(
        deps_path,
        _wrap_top_level(
            {"dep-x": {"profiles": {"init": {"profile": "bogus"}}}}
        ),
    )
    rc, _, _ = _run_cli(deps_path)
    assert rc == 1


def test_main_prints_findings_to_stdout(tmp_path: pathlib.Path) -> None:
    """Cross-component convention: validation findings → stdout; harness-level
    errors → stderr (parallel to 1.2 / 1.3 / 1.5)."""
    deps_path = tmp_path / "dependencies.yaml"
    _write_yaml(
        deps_path,
        _wrap_top_level(
            {"dep-x": {"profiles": {"init": {"profile": "bogus"}}}}
        ),
    )
    rc, out, err = _run_cli(deps_path)
    assert rc == 1
    assert "bogus" in out
    assert "ERROR:" in out
    # stderr stays empty for finding-emission paths.
    assert err == ""


# --------------------------------------------------------------------------- #
# Cross-story seam (AC-5)                                                     #
# --------------------------------------------------------------------------- #


def test_enumeration_check_picks_up_dependencies_yaml() -> None:
    """1.5's enumeration_check auto-discovers schemas/dependencies.yaml AND
    (post-Story-4.10) schemas/escalation-bundles/*.yaml when each lands. Per
    AC-5: passing references include the dependencies.yaml-resolved markers
    (env-setup-failed, mobile-blocked, LAD-skipped × 2) AND the post-Story-
    4.10 escalation-bundle-resolved markers (env-setup-failed × 1 from
    env_setup_diagnostic.marker_class; Tier-3-not-configured × 1 from the
    verification-fail tier_3_not_configured_markers items.marker_class.const;
    plan-drift-detected × 1 from $defs/plan_drift_pointer.marker_class.const;
    smoke-first-abort × 1 from smoke_first_abort_marker.marker_class.const);
    no AC-2 / Story-4.10 deferral notes (both directories present).

    This test IS the cross-story seam contract — it explicitly imports the
    1.5 module and exercises its CLI surface against the canonical schemas.
    """
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = enumeration_check.main([])
    assert rc == 0, f"enumeration-check failed: stdout={out.getvalue()!r} stderr={err.getvalue()!r}"

    text = out.getvalue()
    # Post-Story-14.1 review (marker_class: env-setup-failed added to git init): 14 passing + 21 orphans, no deferral note.
    # Story 12.2 (Sprint Change Proposal 2026-05-18 — validation-
    # responsibility-boundary correction) retired the two
    # `configured-but-api-key-missing` `emits_marker: LAD-skipped`
    # entries from `lad.profiles.{init,runtime}.sub_classifications`.
    # The two `LAD-skipped` enumerated references in dependencies.yaml
    # disappear → passing-reference count drops from 15 to 13. The
    # `LAD-skipped` marker class itself is preserved in
    # `schemas/marker-taxonomy.yaml` (closed-set marker-taxonomy v1
    # invariant per AC-9 + Epic 8 retro) but now has no schema-side
    # consumer; it lands in the orphan bucket → orphan count rises
    # from 20 to 21.
    # The 13 passing references break down as:
    #   dependencies.yaml: env-setup-failed ×5 (git init + claude-code init +
    #                        bmad-core init + tea-module init +
    #                        playwright-mcp web runtime),
    #                       mobile-blocked ×2 (mobile-mcp mobile init
    #                        + mobile-mcp mobile runtime),
    #                       playwright-mcp-unavailable ×1
    #                       (playwright-mcp web init) = 7 refs
    #   escalation-bundles: env-setup-failed ×1, Tier-3-not-configured
    #                        ×1, plan-drift-detected ×1,
    #                        smoke-first-abort ×1,
    #                        retry-budget-exhausted ×1,
    #                        scope-assertion-violation ×1 = 6 refs
    # Total: 14 references. Orphans: 21 (LAD-skipped joins the orphan
    # bucket post-Story-12.2 since the dependencies.yaml emission
    # references were retired; the substrate-side emission via
    # `four_layer_review_dispatch._LAD_MID_RUN_MCP_UNAVAILABLE_DIAGNOSTIC`
    # is the runtime path and is outside enumeration-check's reconciliation
    # scope).
    # If a future story adds markers to marker-taxonomy.yaml or new
    # marker_class references to dependencies.yaml or to schemas/escalation-
    # bundles/*.yaml, update this count accordingly.
    # Post-Story-14.3 review: marker `worktree-stale-lock` newly enumerated
    # in `schemas/marker-taxonomy.yaml` via PATCH bump 1.6 → 1.7; zero
    # `dependencies.yaml` reference (the marker is SessionStart-emission,
    # NOT a dependency-failure-profile dispatch surface — emitted by
    # `session_start_reattach.evaluate_reattach`'s fifth branch when a
    # crashed worktree leaves a stale `_bmad/automation/locks/<story-id>.lock`
    # file). Structurally an orphan from the enumeration_check perspective;
    # the orphan-count increment 21 → 22 is the load-bearing witness that
    # the taxonomy edit landed.
    # Post-Story-14.5 review: marker `parallel-story-state-pollution` newly
    # enumerated in `schemas/marker-taxonomy.yaml` via PATCH bump 1.7 → 1.8;
    # zero `dependencies.yaml` reference, zero `escalation-bundles/*.yaml`
    # reference, zero `orchestrator-event.yaml` decision-point reference (the
    # marker is emitted at parallel-dispatch RUNTIME by Epic 18 Story 18.2,
    # NOT by any init / dependency-failure-profile dispatcher). Structurally
    # an orphan from the enumeration_check perspective, exactly like
    # `worktree-stale-lock`; the orphan-count increment 22 → 23 is the
    # load-bearing witness that the Story 14.5 taxonomy edit landed.
    # Post-Story-15.2 review: marker `epic-budget-exhausted` newly enumerated
    # in `schemas/marker-taxonomy.yaml` via PATCH bump 1.9 → 1.10; zero
    # `dependencies.yaml` reference, zero `escalation-bundles/*.yaml` reference,
    # zero `orchestrator-event.yaml` decision-point reference (the marker is
    # emitted at epic-loop RUNTIME by `epic_lifecycle.run_epic_loop` into the
    # epic-run-state `active_markers`, NOT by any init / dependency-failure-
    # profile dispatcher). Structurally an orphan from the enumeration_check
    # perspective, exactly like `worktree-stale-lock` /
    # `parallel-story-state-pollution`; the orphan-count increment 23 → 24 is
    # the load-bearing witness that the Story 15.2 taxonomy edit landed.
    #
    # Post-Story-16.2 review: marker `sprint-escalation-rate-exceeded` newly
    # enumerated via PATCH bump 1.10 → 1.11; zero `dependencies.yaml` /
    # `escalation-bundles/*.yaml` / `orchestrator-event.yaml` reference (emitted
    # at sprint-loop RUNTIME by `sprint_lifecycle.run_sprint_loop`). Structurally
    # an orphan exactly like `epic-budget-exhausted`; the orphan-count increment
    # 24 → 25 is the load-bearing witness that the Story 16.2 taxonomy edit landed.
    #
    # Post-Story-24.1 review: marker `parallel-dispatch-infra-failed` newly
    # enumerated via MINOR bump 1.11 → 1.12; zero `dependencies.yaml` /
    # `escalation-bundles/*.yaml` / `orchestrator-event.yaml` reference (emitted
    # at parallel-dispatch RUNTIME by `parallel_dispatch._emit_infra_failure`).
    # Structurally an orphan exactly like `epic-budget-exhausted` /
    # `parallel-story-state-pollution`; the orphan-count increment 25 → 26 is the
    # load-bearing witness that the Story 24.1 taxonomy edit landed.
    #
    # Post-Story-19.3 review: THREE new a11y-audit evidence markers
    # (`a11y-baseline-stale` / `a11y-delta-exceeded` / `a11y-delta-mode-unstable`)
    # newly enumerated via MINOR bump 1.13 → 1.14; each has ZERO `dependencies.yaml`
    # reference (the activated `axe-core` entry carries NO `marker_class` — the
    # markers are QA-wrapper-emitted evidence markers, not dependency-availability
    # markers), zero `escalation-bundles/*.yaml` / `orchestrator-event.yaml`
    # reference (runtime emission lands in Story 19.4). The `axe-core` dependency
    # entry adds NO passing reference (passing stays 14); the three markers join
    # the orphan bucket → orphan-count increment 26 → 29 is the load-bearing
    # witness that the Story 19.3 taxonomy + dependency edits landed.
    #
    # Post-Story-19.5 review: TWO visual-regression evidence markers
    # (`visual-regression-delta-exceeded` / `visual-regression-baseline-missing`)
    # joined the orphan bucket (QA-wrapper-emitted evidence; the `pixelmatch`
    # dependency entry carries NO `marker_class`); orphan-count 29 → 31.
    #
    # Post-Story-20.1 review: ONE plan-rederivation evidence marker
    # (`plan-rederivation-drift-detected`) newly enumerated via PATCH bump
    # 1.15 → 1.16; zero `dependencies.yaml` / `escalation-bundles/*.yaml` /
    # `orchestrator-event.yaml` reference (a QA-evidence marker emitted at QA
    # RUNTIME by `qa_plan_rederivation.surface_plan_rederivation_cross_check`,
    # exactly like `plan-drift-detected`, which also has no counterpart). The
    # marker joins the orphan bucket → orphan-count increment 31 → 32 is the
    # load-bearing witness that the Story 20.1 taxonomy edit landed.
    assert "Summary: 14 passing reference(s), 0 missing reference(s), 32 orphan marker class(es)" in text
    assert "deferred to story 1.6" not in text
    assert "deferred to story 4.10" not in text


# --------------------------------------------------------------------------- #
# Pydantic v2 frozen-model discipline                                         #
# --------------------------------------------------------------------------- #


def test_validation_finding_is_frozen() -> None:
    f = ValidationFinding(pointer="/x", message="m", remediation="r")
    with pytest.raises(ValidationError):
        f.message = "other"  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# NFR-O5 named-invariant diagnostic shape                                     #
# --------------------------------------------------------------------------- #


def test_finding_message_names_pointer_invariant_remediation() -> None:
    """Per NFR-O5: every finding names (a) JSON-pointer path, (b) violated
    invariant verbatim, (c) one-line remediation pointer naming the contract."""
    raw = _wrap_top_level(
        {"dep-x": {"profiles": {"init": {"profile": "bogus"}}}}
    )
    findings = validate_dependencies(raw, "synthetic.yaml")
    assert findings
    f = findings[0]
    # (a) pointer:
    assert f.pointer.startswith("/dependencies/")
    # (b) invariant verbatim — names the bogus value AND the closed enum:
    assert "bogus" in f.message
    assert "must be one of total-block, graceful-degrade, opt-in-skip" in f.message
    # (c) remediation names the contract:
    assert "SDN-001" in f.remediation


def test_format_findings_renders_pointer_and_remediation(tmp_path: pathlib.Path) -> None:
    """format_findings output line includes pointer + message + remediation."""
    f = ValidationFinding(
        pointer="/dependencies/x/profiles/init/profile",
        message="unknown failure_profile value 'bogus' (must be one of total-block, graceful-degrade, opt-in-skip)",
        remediation="(per SDN-001 / NFR-I3)",
    )
    rendered = format_findings([f], "synthetic.yaml")
    assert "Dependencies schema validation (SDN-001): synthetic.yaml" in rendered
    assert "ERROR: 1 shape-rule violation(s)." in rendered
    assert "/dependencies/x/profiles/init/profile" in rendered
    assert "(per SDN-001 / NFR-I3)" in rendered


# --------------------------------------------------------------------------- #
# load_dependencies helper                                                    #
# --------------------------------------------------------------------------- #


def test_load_dependencies_returns_dict() -> None:
    """The on-disk canonical schema loads + shape-validates cleanly."""
    raw = load_dependencies(CANONICAL_DEPENDENCIES_PATH)
    assert isinstance(raw, dict)
    assert raw["schema_version"] == "1.7"
    deps = raw["dependencies"]
    # Story 14.1 AC-6: git entry present with version_floor "2.5";
    # both init + runtime profiles total-block; operator-actionable
    # diagnostic prose names `git --version` per ADR-009.
    assert "git" in deps
    assert deps["git"]["version_floor"] == "2.5"
    assert deps["git"]["profiles"]["init"]["profile"] == "total-block"
    assert deps["git"]["profiles"]["runtime"]["profile"] == "total-block"
    assert "git --version" in deps["git"]["profiles"]["init"]["diagnostic"]
    # Story 10.1: lad activated — phase: "1.5" removed; all six dependencies
    # are now phase-free (mobile-mcp activated by Story 9.1; lad by Story 10.1).
    assert "phase" not in deps["claude-code"]
    assert "phase" not in deps["bmad-core"]
    assert "phase" not in deps["tea-module"]
    assert "phase" not in deps["playwright-mcp"]
    assert "phase" not in deps["mobile-mcp"]
    assert "phase" not in deps["lad"]
    # Story 9.1 AC-6: version_floor pinned to the concrete value per ADR-007.
    assert deps["mobile-mcp"]["version_floor"] == "0.0.54"
    # Story 10.1 AC-1: version_floor pinned to the resolved upstream short
    # commit SHA per ADR-008.
    assert deps["lad"]["version_floor"] == "bb47e9e"
    # Story 12.2 + Sprint Change Proposal 2026-05-18: the prior
    # ``configured-but-api-key-missing`` sub_classification entries on
    # both init + runtime profiles were retired (validation-
    # responsibility-boundary correction — third-party credential
    # validation belongs at the upstream `lad_mcp_server` MCP boundary,
    # not in bmad-autopilot). Each profile's sub_classifications list
    # collapses to the remaining ``unconfigured`` entry (``silent:
    # true``); no other lad sub_classification entries should remain.
    lad_init_sc = deps["lad"]["profiles"]["init"]["sub_classifications"]
    assert lad_init_sc == [{"condition": "unconfigured", "silent": True}]
    lad_runtime_sc = deps["lad"]["profiles"]["runtime"]["sub_classifications"]
    assert lad_runtime_sc == [{"condition": "unconfigured", "silent": True}]
    # Story 19.3 AC-2 / AC-8a: axe-core activated — Phase-2 a11y-audit dependency
    # entry (opt-in-skip on both init + runtime; version_floor "4.12" pinned per
    # ADR-011 / FR-P2-6; no `phase` field — Phase 2 is current shipping scope).
    # The entry references NO marker_class (the three a11y markers are wrapper-
    # emitted evidence markers / taxonomy orphans, not availability markers).
    assert "axe-core" in deps
    assert deps["axe-core"]["version_floor"] == "4.12"
    assert "phase" not in deps["axe-core"]
    assert deps["axe-core"]["profiles"]["init"]["profile"] == "opt-in-skip"
    assert deps["axe-core"]["profiles"]["runtime"]["profile"] == "opt-in-skip"
    assert deps["axe-core"]["profiles"]["init"]["sub_classifications"] == [
        {"condition": "unconfigured", "silent": True}
    ]
    assert deps["axe-core"]["profiles"]["runtime"]["sub_classifications"] == [
        {"condition": "unconfigured", "silent": True}
    ]
    assert "marker_class" not in deps["axe-core"]["profiles"]["init"]
    assert "marker_class" not in deps["axe-core"]["profiles"]["runtime"]
    # Per AC-4: per-lifecycle-phase variance verifiable on playwright-mcp + mobile-mcp.
    assert (
        deps["playwright-mcp"]["by_project_type"]["web"]["profiles"]["init"]["profile"]
        == "total-block"
    )
    assert (
        deps["playwright-mcp"]["by_project_type"]["web"]["profiles"]["runtime"]["profile"]
        == "graceful-degrade"
    )
    assert (
        deps["playwright-mcp"]["by_project_type"]["web"]["profiles"]["runtime"]["marker_class"]
        == "env-setup-failed"
    )
    assert (
        deps["mobile-mcp"]["by_project_type"]["mobile"]["profiles"]["init"]["profile"]
        == "total-block"
    )
    assert (
        deps["mobile-mcp"]["by_project_type"]["mobile"]["profiles"]["runtime"]["profile"]
        == "graceful-degrade"
    )
    assert (
        deps["mobile-mcp"]["by_project_type"]["mobile"]["profiles"]["runtime"]["marker_class"]
        == "mobile-blocked"
    )


def test_pixelmatch_dependency_entry() -> None:
    """Story 19.5 AC-2: the `pixelmatch` Phase-2 visual-regression dependency
    entry is present with the opt-in-skip shape (version_floor "7.2", no `phase`,
    no `marker_class` — the wrapper-emitted-evidence-marker precedent), both init
    + runtime profiles `opt-in-skip` with `unconfigured`/`silent: true`; the live
    schema_version is "1.7" and the validator finds zero issues."""
    repo_root = find_repo_root()
    deps_path = repo_root / "schemas" / "dependencies.yaml"
    raw = load_dependencies(deps_path)
    assert raw["schema_version"] == "1.7"
    assert validate_dependencies(raw, str(deps_path)) == []
    deps = raw["dependencies"]
    assert "pixelmatch" in deps
    assert deps["pixelmatch"]["version_floor"] == "7.2"
    assert "phase" not in deps["pixelmatch"]
    assert deps["pixelmatch"]["profiles"]["init"]["profile"] == "opt-in-skip"
    assert deps["pixelmatch"]["profiles"]["runtime"]["profile"] == "opt-in-skip"
    assert deps["pixelmatch"]["profiles"]["init"]["sub_classifications"] == [
        {"condition": "unconfigured", "silent": True}
    ]
    assert deps["pixelmatch"]["profiles"]["runtime"]["sub_classifications"] == [
        {"condition": "unconfigured", "silent": True}
    ]
    assert "marker_class" not in deps["pixelmatch"]["profiles"]["init"]
    assert "marker_class" not in deps["pixelmatch"]["profiles"]["runtime"]


def test_extended_fixture_git_entry_state() -> None:
    """Story 14.1 AC-7 / Story 19.3 AC-7 — extended-fixture witness (ADR-009 + ADR-011 activation).

    Loads the Story 7.3 extended fixture and verifies the activated shapes:
    Story 14.1 (git, version_floor "2.5", total-block on both profiles,
    ``git --version`` diagnostic) and Story 19.3 (axe-core, version_floor
    "4.12", opt-in-skip on both profiles, unconfigured/silent
    sub_classifications). Substrate component 5 (fixture-coverage) exercises
    both activated entries' structural validity; the validator returns zero
    findings on the fixture.
    """
    fixture_path = (
        pathlib.Path(__file__).resolve().parent
        / "fixtures"
        / "init_preconditions"
        / "dependencies-fixture-extended.yaml"
    )
    raw = load_dependencies(fixture_path)
    assert validate_dependencies(raw, str(fixture_path)) == []
    assert raw["schema_version"] == "1.7"
    deps = raw["dependencies"]
    assert "git" in deps
    assert deps["git"]["version_floor"] == "2.5"
    assert deps["git"]["profiles"]["init"]["profile"] == "total-block"
    assert deps["git"]["profiles"]["runtime"]["profile"] == "total-block"
    assert "git --version" in deps["git"]["profiles"]["init"]["diagnostic"]
    # Story 19.3 AC-7: axe-core fixture-coverage — the activated a11y-audit
    # dependency entry rides the extended fixture (byte-identical opt-in-skip
    # shape to the live dependencies.yaml entry); the validator returns zero
    # findings on the fixture (asserted above).
    assert "axe-core" in deps
    assert deps["axe-core"]["version_floor"] == "4.12"
    assert "phase" not in deps["axe-core"]
    assert deps["axe-core"]["profiles"]["init"]["profile"] == "opt-in-skip"
    assert deps["axe-core"]["profiles"]["runtime"]["profile"] == "opt-in-skip"
    assert deps["axe-core"]["profiles"]["init"]["sub_classifications"] == [
        {"condition": "unconfigured", "silent": True}
    ]
    assert deps["axe-core"]["profiles"]["runtime"]["sub_classifications"] == [
        {"condition": "unconfigured", "silent": True}
    ]


def test_extended_fixture_mobile_mcp_activated_state() -> None:
    """Story 9.1 AC-7 — activation-state fixture witness.

    Loads the Story 7.3 extended fixture (which now includes a Story 9.1
    activation-state ``mobile-mcp`` entry) and verifies the activated shape:
    ``phase`` field absent, ``version_floor`` pinned per ADR-007, and the
    mobile-project runtime profile carries ``marker_class: mobile-blocked``.
    Ensures the activation-state fixture row is structurally valid; the added
    ``mobile-mcp`` entry provides substrate component 5 (fixture-coverage)
    enumeration coverage for ``mobile-blocked`` in the Phase 1.5 steady-state
    configuration.
    """
    fixture_path = (
        pathlib.Path(__file__).resolve().parent
        / "fixtures"
        / "init_preconditions"
        / "dependencies-fixture-extended.yaml"
    )
    raw = load_dependencies(fixture_path)
    assert validate_dependencies(raw, str(fixture_path)) == []
    deps = raw["dependencies"]
    assert "mobile-mcp" in deps
    assert "phase" not in deps["mobile-mcp"]
    assert deps["mobile-mcp"]["version_floor"] == "0.0.54"
    mobile_profiles = deps["mobile-mcp"]["by_project_type"]["mobile"]["profiles"]
    assert mobile_profiles["init"]["profile"] == "total-block"
    assert mobile_profiles["runtime"]["profile"] == "graceful-degrade"
    assert mobile_profiles["runtime"]["marker_class"] == "mobile-blocked"


def test_extended_fixture_lad_activated_state() -> None:
    """Story 10.1 AC-7 — activated-lad fixture witness (post-Story-12.2).

    Loads the Story 7.3 extended fixture (which now includes a Story 10.1
    activated-state ``lad`` entry) and verifies the activated shape:
    ``phase`` field absent, ``version_floor`` pinned to the resolved
    upstream short SHA per ADR-008, both init + runtime ``opt-in-skip``
    profiles intact. Post-Story-12.2 + Sprint Change Proposal 2026-05-18
    (validation-responsibility-boundary correction), the prior
    ``configured-but-api-key-missing`` sub_classification entries (one
    per profile) are RETIRED; each profile's sub_classifications list
    collapses to the remaining ``unconfigured`` entry (``silent: true``).
    Substrate component 5 (fixture-coverage) still exercises the
    activated-lad fixture row's structural validity; ``LAD-skipped``
    marker reachability now flows through the substrate's mid-run
    emission path in ``four_layer_review_dispatch`` rather than the
    schema's `emits_marker` field.
    """
    fixture_path = (
        pathlib.Path(__file__).resolve().parent
        / "fixtures"
        / "init_preconditions"
        / "dependencies-fixture-extended.yaml"
    )
    raw = load_dependencies(fixture_path)
    assert validate_dependencies(raw, str(fixture_path)) == []
    deps = raw["dependencies"]
    assert "lad" in deps
    assert "phase" not in deps["lad"]
    assert deps["lad"]["version_floor"] == "bb47e9e"

    init_profile = deps["lad"]["profiles"]["init"]
    assert init_profile["profile"] == "opt-in-skip"
    assert init_profile["sub_classifications"] == [
        {"condition": "unconfigured", "silent": True}
    ]

    runtime_profile = deps["lad"]["profiles"]["runtime"]
    assert runtime_profile["profile"] == "opt-in-skip"
    assert runtime_profile["sub_classifications"] == [
        {"condition": "unconfigured", "silent": True}
    ]


def test_load_dependencies_raises_on_invalid_shape(tmp_path: pathlib.Path) -> None:
    deps_path = tmp_path / "dependencies.yaml"
    _write_yaml(
        deps_path,
        _wrap_top_level(
            {"dep-x": {"profiles": {"init": {"profile": "bogus"}}}}
        ),
    )
    with pytest.raises(RuntimeError) as exc:
        load_dependencies(deps_path)
    assert "failed SDN-001 shape validation" in str(exc.value)
    assert "bogus" in str(exc.value)


def test_load_dependencies_raises_on_top_level_non_mapping(tmp_path: pathlib.Path) -> None:
    deps_path = tmp_path / "dependencies.yaml"
    deps_path.write_text("- item-a\n- item-b\n", encoding="utf-8")
    with pytest.raises(RuntimeError) as exc:
        load_dependencies(deps_path)
    assert "did not parse to a YAML mapping" in str(exc.value)


# --------------------------------------------------------------------------- #
# Defensive shape rules (uncovered branches; raise per-branch coverage)       #
# --------------------------------------------------------------------------- #


def test_non_string_schema_version_rejected() -> None:
    raw = {"schema_version": 1.0, "dependencies": {}}
    findings = validate_dependencies(raw, "synthetic.yaml")
    assert any(
        f.pointer == "/schema_version" and "must be a string" in f.message
        for f in findings
    ), findings


def test_non_dict_dependencies_rejected() -> None:
    raw = {"schema_version": "1.0", "dependencies": ["not", "a", "mapping"]}
    findings = validate_dependencies(raw, "synthetic.yaml")
    assert any(
        f.pointer == "/dependencies" and "must be a mapping" in f.message
        for f in findings
    ), findings


def test_validate_dependencies_top_level_non_mapping_returns_root_finding() -> None:
    """Direct-API misuse path: validate_dependencies passed a non-dict surfaces
    a single root-level finding rather than crashing (programmer-bug guard)."""
    findings = validate_dependencies("not a dict", "synthetic.yaml")  # type: ignore[arg-type]
    assert len(findings) == 1
    assert findings[0].pointer == "<root>"
    assert "top-level must be a YAML mapping" in findings[0].message


def test_non_dict_profiles_map_rejected() -> None:
    raw = _wrap_top_level({"dep-bad": {"profiles": "not-a-mapping"}})
    findings = validate_dependencies(raw, "synthetic.yaml")
    assert any(
        f.pointer == "/dependencies/dep-bad/profiles"
        and "'profiles' must be a mapping" in f.message
        for f in findings
    ), findings


def test_non_dict_profile_spec_rejected() -> None:
    raw = _wrap_top_level({"dep-bad": {"profiles": {"init": "not-a-mapping"}}})
    findings = validate_dependencies(raw, "synthetic.yaml")
    assert any(
        f.pointer == "/dependencies/dep-bad/profiles/init"
        and "profile spec must be a mapping" in f.message
        for f in findings
    ), findings


def test_non_dict_by_project_type_rejected() -> None:
    raw = _wrap_top_level({"dep-bad": {"by_project_type": "not-a-mapping"}})
    findings = validate_dependencies(raw, "synthetic.yaml")
    assert any(
        f.pointer == "/dependencies/dep-bad/by_project_type"
        and "'by_project_type' must be a mapping" in f.message
        for f in findings
    ), findings


def test_non_dict_project_type_entry_rejected() -> None:
    raw = _wrap_top_level(
        {"dep-bad": {"by_project_type": {"web": "not-a-mapping"}}}
    )
    findings = validate_dependencies(raw, "synthetic.yaml")
    assert any(
        f.pointer == "/dependencies/dep-bad/by_project_type/web"
        and "project-type entry must be a mapping" in f.message
        for f in findings
    ), findings


def test_project_type_entry_missing_profiles_rejected() -> None:
    raw = _wrap_top_level({"dep-bad": {"by_project_type": {"web": {}}}})
    findings = validate_dependencies(raw, "synthetic.yaml")
    assert any(
        f.pointer == "/dependencies/dep-bad/by_project_type/web/profiles"
        and "missing required field 'profiles'" in f.message
        for f in findings
    ), findings


def test_project_type_entry_unknown_field_rejected() -> None:
    raw = _wrap_top_level(
        {
            "dep-bad": {
                "by_project_type": {
                    "web": {
                        "profiles": {"init": {"profile": "opt-in-skip"}},
                        "rogue": "x",
                    }
                }
            }
        }
    )
    findings = validate_dependencies(raw, "synthetic.yaml")
    assert any(
        f.pointer == "/dependencies/dep-bad/by_project_type/web/rogue"
        and "unknown field 'rogue'" in f.message
        for f in findings
    ), findings


def test_non_list_sub_classifications_rejected() -> None:
    raw = _wrap_top_level(
        {
            "dep-bad": {
                "profiles": {
                    "init": {
                        "profile": "opt-in-skip",
                        "sub_classifications": {"not": "a list"},
                    }
                }
            }
        }
    )
    findings = validate_dependencies(raw, "synthetic.yaml")
    assert any(
        "must be a sequence" in f.message
        and f.pointer.endswith("/sub_classifications")
        for f in findings
    ), findings


def test_non_dict_sub_classification_entry_rejected() -> None:
    raw = _wrap_top_level(
        {
            "dep-bad": {
                "profiles": {
                    "init": {
                        "profile": "opt-in-skip",
                        "sub_classifications": ["not-a-mapping"],
                    }
                }
            }
        }
    )
    findings = validate_dependencies(raw, "synthetic.yaml")
    assert any(
        "must be a mapping" in f.message
        and f.pointer.endswith("/sub_classifications/0")
        for f in findings
    ), findings


def test_non_string_condition_rejected() -> None:
    raw = _wrap_top_level(
        {
            "dep-bad": {
                "profiles": {
                    "init": {
                        "profile": "opt-in-skip",
                        "sub_classifications": [
                            {"condition": 42, "silent": True}
                        ],
                    }
                }
            }
        }
    )
    findings = validate_dependencies(raw, "synthetic.yaml")
    assert any(
        "'condition' must be a string" in f.message for f in findings
    ), findings


def test_non_string_emits_marker_rejected() -> None:
    raw = _wrap_top_level(
        {
            "dep-bad": {
                "profiles": {
                    "init": {
                        "profile": "opt-in-skip",
                        "sub_classifications": [
                            {"condition": "x", "emits_marker": 42}
                        ],
                    }
                }
            }
        }
    )
    findings = validate_dependencies(raw, "synthetic.yaml")
    assert any(
        "'emits_marker' must be a string" in f.message for f in findings
    ), findings


def test_silent_false_rejected() -> None:
    raw = _wrap_top_level(
        {
            "dep-bad": {
                "profiles": {
                    "init": {
                        "profile": "opt-in-skip",
                        "sub_classifications": [
                            {"condition": "x", "silent": False}
                        ],
                    }
                }
            }
        }
    )
    findings = validate_dependencies(raw, "synthetic.yaml")
    assert any(
        "'silent' must be the literal boolean true" in f.message for f in findings
    ), findings


def test_missing_profile_field_in_spec_rejected() -> None:
    raw = _wrap_top_level(
        {"dep-bad": {"profiles": {"init": {"diagnostic": "x"}}}}
    )
    findings = validate_dependencies(raw, "synthetic.yaml")
    assert any(
        f.pointer == "/dependencies/dep-bad/profiles/init/profile"
        and "missing required field 'profile'" in f.message
        for f in findings
    ), findings


def test_format_findings_zero_findings_renders_ok() -> None:
    rendered = format_findings([], "schemas/dependencies.yaml")
    assert "OK: 0 findings." in rendered
    assert "ERROR" not in rendered
