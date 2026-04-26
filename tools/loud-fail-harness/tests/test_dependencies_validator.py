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
    """1.5's enumeration_check auto-discovers schemas/dependencies.yaml when
    it lands. Per AC-5: 4 passing references (env-setup-failed, mobile-blocked,
    LAD-skipped × 2); orphan list shrinks to 24 (27 taxonomy − 3 distinct
    referenced markers); the AC-2 deferral note is absent.

    This test IS the cross-story seam contract — it explicitly imports the
    1.5 module and exercises its CLI surface against the canonical schemas.
    """
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = enumeration_check.main([])
    assert rc == 0, f"enumeration-check failed: stdout={out.getvalue()!r} stderr={err.getvalue()!r}"

    text = out.getvalue()
    # AC-5: 4 passing + 24 orphans, no deferral note.
    # Arithmetic: 27 total taxonomy markers − 3 distinct referenced markers
    # (env-setup-failed, mobile-blocked, LAD-skipped) = 24 orphans.
    # If a future story adds markers to marker-taxonomy.yaml or new marker_class
    # references to dependencies.yaml, update this count accordingly.
    assert "Summary: 4 passing reference(s), 0 missing reference(s), 24 orphan marker class(es)" in text
    assert "deferred to story 1.6" not in text


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
    assert raw["schema_version"] == "1.0"
    deps = raw["dependencies"]
    # Per AC-4: phase: "1.5" present on mobile-mcp + lad; absent on the four MVP entries.
    assert "phase" not in deps["claude-code"]
    assert "phase" not in deps["bmad-core"]
    assert "phase" not in deps["tea-module"]
    assert "phase" not in deps["playwright-mcp"]
    assert deps["mobile-mcp"]["phase"] == "1.5"
    assert deps["lad"]["phase"] == "1.5"
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
