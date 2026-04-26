"""Contract-coverage matrix for the pluggability no-cross-references CI gate (story 1.10a).

This docstring IS the contract-coverage checklist required by AC-9. Reviewers
verify every row maps to at least one passing test in this module. The matrix
is review-enforced, NOT CI-enforced (parallel to story 1.2 / 1.3 / 1.4 / 1.5 /
1.6 / 1.7 / 1.8 / 1.9 AC discipline).

Baseline-zero classification cases (AC-2, AC-5):
    [x] agents/ does not exist                                    → test_baseline_zero_no_agents_dir
    [x] agents/ exists but is empty                               → test_baseline_zero_empty_agents_dir

Single / two / four-specialist clean-corpus cases (AC-2, AC-5):
    [x] single specialist — no possible cross-references          → test_single_specialist_no_violations
    [x] two specialists — no cross-references between them        → test_two_specialists_no_violations
    [x] four specialists — MVP-close forward simulation           → test_four_specialists_no_violations

Rule 1 (path-form) cases (AC-3, AC-5, AC-6):
    [x] basic path-form violation                                 → test_rule1_path_form_basic_violation
    [x] match inside markdown link                                → test_rule1_path_form_inside_markdown_link
    [x] no match — substring superset (.mds)                      → test_rule1_path_form_no_match_substring_superset
    [x] no match — self-reference                                 → test_rule1_path_form_self_reference_excluded
    [x] no match — .bak extension ((?!\\w|[.]\\w) not \\b)         → test_rule1_path_form_no_match_bak_extension

Rule 2 (slug-form) cases (AC-4, AC-5, AC-6):
    [x] basic slug-form violation                                 → test_rule2_slug_form_basic_violation
    [x] multiple matches per file                                 → test_rule2_slug_form_multiple_matches_per_file
    [x] single-word slug `qa` deliberately excluded               → test_rule2_slug_form_single_word_slug_qa_excluded
    [x] kebab-extension matches (boundary fires)                  → test_rule2_slug_form_kebab_extension_matches
    [x] concatenated identifier — no boundary, no match           → test_rule2_slug_form_concatenated_no_match
    [x] no match — self-reference                                 → test_rule2_slug_form_self_reference_excluded
    [x] not suppressed — slug in superstring prefix (myagents/)   → test_rule2_slug_form_not_suppressed_in_superstring_prefix

Permitted-reference cases (AC-3, AC-4 by-construction allowlist):
    [x] substrate path (tools/loud-fail-harness/...)              → test_permitted_substrate_path_no_violation
    [x] schema path (schemas/...)                                 → test_permitted_schema_path_no_violation
    [x] BMAD-core skill name (bmad-dev-story)                     → test_permitted_bmad_core_skill_no_violation
    [x] marker class with `qa-` prefix (qa-failed)                → test_permitted_marker_class_qa_prefix_no_violation
    [x] section name (## QA Behavioral Plan)                      → test_permitted_section_name_qa_behavioral_plan_no_violation
    [x] lifecycle state (qa)                                      → test_permitted_lifecycle_state_qa_no_violation
    [x] agent-file-as-data placeholder (agents/<X>.md)            → test_permitted_agent_file_as_data_placeholder_no_violation

Mixed cases (AC-5):
    [x] passing + violation in same run                           → test_mixed_passing_and_violation_in_same_run
    [x] both rules fire on same file (different referenced)       → test_both_rules_fire_on_same_offending_file

Discovery edge cases (AC-2, AC-9):
    [x] subdirectory specialist file NOT discovered               → test_subdirectory_specialist_not_discovered
    [x] non-.md file ignored                                      → test_non_md_file_ignored
    [x] non-.md file with .md substring ignored (.markdown)       → test_non_md_file_with_md_substring_ignored
    [x] empty file (0 bytes)                                      → test_empty_file_zero_bytes

Loud-fail / harness-level errors (AC-6, AC-9, Pattern 5):
    [x] unreadable file (chmod 000)                               → test_loud_fail_on_unreadable_file
    [x] non-UTF-8 file                                            → test_loud_fail_on_non_utf8_file
    [x] agents_dir exists but unreadable (chmod 000)              → test_loud_fail_on_unreadable_agents_dir

Determinism + serialization (AC-9):
    [x] run_pluggability_gate is byte-identical across runs       → test_determinism_repeated_invocation
    [x] GateResult.model_dump_json byte-identical                 → test_gate_result_json_serialization_stable

Pydantic v2 frozen-model discipline (AC-9):
    [x] Reference frozen + hashable                               → test_reference_is_frozen_and_hashable
    [x] CrossReferenceFinding frozen + hashable                   → test_cross_reference_finding_is_frozen_and_hashable
    [x] GateResult frozen; not hashable (list fields)             → test_gate_result_frozen_not_hashable

CLI / main exit-code matrix (AC-6, AC-9):
    [x] canonical corpus baseline-zero (real agents/ dir)         → test_canonical_corpus_baseline_zero
    [x] main --help resolves to argparse                          → test_main_help_resolves
    [x] main with custom --agents-dir test-injection              → test_main_with_custom_agents_dir

Diagnostic-prose verbatim (AC-7):
    [x] format_findings matches AC-7 verbatim                     → test_format_findings_matches_ac7_verbatim

Coverage (AC-9):
    [x] pluggability_gate.py module-level statement coverage ≥ 90% → review-enforced; not a CI gate
"""

from __future__ import annotations

import io
import os
import pathlib
import sys

import pytest
from pydantic import ValidationError

from loud_fail_harness.pluggability_gate import (
    CrossReferenceFinding,
    GateResult,
    Reference,
    discover_specialists,
    find_cross_references_path_form,
    find_cross_references_slug_form,
    main,
    run_pluggability_gate,
)

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _write_specialist(
    path: pathlib.Path,
    *,
    body: str = "# Specialist\n",
) -> pathlib.Path:
    """Write ``body`` as UTF-8 to ``path``. Returns ``path`` for chaining."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _make_agents_dir(
    tmp_path: pathlib.Path,
    *,
    specialists: dict[str, str],
    create_dir: bool = True,
) -> pathlib.Path:
    """Create ``tmp_path/agents/`` populated with ``{filename: body}``."""
    agents_dir = tmp_path / "agents"
    if create_dir:
        agents_dir.mkdir(parents=True, exist_ok=True)
    for filename, body in specialists.items():
        target = agents_dir / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_specialist(target, body=body)
    return agents_dir


def _capture_main(args: list[str]) -> tuple[int, str, str]:
    """Run ``main(args)`` capturing stdout + stderr."""
    out = io.StringIO()
    err = io.StringIO()
    saved_stdout = sys.stdout
    saved_stderr = sys.stderr
    sys.stdout = out
    sys.stderr = err
    try:
        rc = main(args)
    finally:
        sys.stdout = saved_stdout
        sys.stderr = saved_stderr
    return rc, out.getvalue(), err.getvalue()


# ---------------------------------------------------------------------------
# Baseline-zero classification cases
# ---------------------------------------------------------------------------


def test_baseline_zero_no_agents_dir(tmp_path: pathlib.Path) -> None:
    """No agents/ directory → 0 passing, 0 violations, exit 0.

    Documents the seam contract with stories 2.8 / 2.9 / 2.10 / 4.x: "the
    gate is correct at story 1.10a's landing time when no specialist
    files exist."
    """
    agents_dir = tmp_path / "agents"  # NOT created
    assert not agents_dir.exists()
    rc, out, _ = _capture_main(["--agents-dir", str(agents_dir)])
    assert rc == 0
    assert (
        "Summary: 0 passing specialist(s), 0 cross-reference violation(s) "
        "across 0 specialist file(s)."
    ) in out
    assert "Pluggability violation:" not in out


def test_baseline_zero_empty_agents_dir(tmp_path: pathlib.Path) -> None:
    """Empty agents/ directory → 0 passing, 0 violations, exit 0."""
    agents_dir = _make_agents_dir(tmp_path, specialists={})
    rc, out, _ = _capture_main(["--agents-dir", str(agents_dir)])
    assert rc == 0
    assert "Summary: 0 passing specialist(s)" in out
    assert "Pluggability violation:" not in out


# ---------------------------------------------------------------------------
# Single / two / four-specialist clean-corpus cases
# ---------------------------------------------------------------------------


def test_single_specialist_no_violations(tmp_path: pathlib.Path) -> None:
    """1 specialist alone → cannot have cross-references; passes cleanly.

    Documents the Epic 2 milestone (story 2.8 lands the first specialist
    alone; the gate must pass).
    """
    agents_dir = _make_agents_dir(
        tmp_path,
        specialists={
            "dev-wrapper.md": "# Dev Wrapper\nWraps bmad-dev-story.\n",
        },
    )
    result = run_pluggability_gate(agents_dir)
    assert len(result.passing) == 1
    assert result.passing[0].specialist_slug == "dev-wrapper"
    assert result.passing[0].file_name == "dev-wrapper.md"
    assert result.cross_reference_violation == []


def test_two_specialists_no_violations(tmp_path: pathlib.Path) -> None:
    """2 specialists with substrate-only references → both pass.

    Documents the Epic 3 milestone (story 3.x lands the second specialist).
    """
    agents_dir = _make_agents_dir(
        tmp_path,
        specialists={
            "dev-wrapper.md": (
                "# Dev Wrapper\nWraps bmad-dev-story (BMAD-core skill).\n"
                "Reads schemas/envelope.schema.yaml.\n"
            ),
            "review-bmad-wrapper.md": (
                "# Review-BMAD Wrapper\nWraps bmad-code-review.\n"
                "Consumes tools/loud-fail-harness/.\n"
            ),
        },
    )
    result = run_pluggability_gate(agents_dir)
    assert [r.specialist_slug for r in result.passing] == [
        "dev-wrapper",
        "review-bmad-wrapper",
    ]
    assert result.cross_reference_violation == []


def test_four_specialists_no_violations(tmp_path: pathlib.Path) -> None:
    """4 specialists (MVP-close forward simulation) → all pass.

    Documents the MVP-close milestone (after story 4.x + 5.x land the
    canonical four specialist set per architecture.md lines 1068-1072).
    """
    agents_dir = _make_agents_dir(
        tmp_path,
        specialists={
            "dev-wrapper.md": "# Dev Wrapper\nWraps bmad-dev-story.\n",
            "review-bmad-wrapper.md": "# Review-BMAD Wrapper\nWraps bmad-code-review.\n",
            "qa.md": "# QA\nFR16-FR25 behavioral verification.\n",
            "lad-wrapper.md": "# LAD Wrapper\nPhase 1.5 external review.\n",
        },
    )
    result = run_pluggability_gate(agents_dir)
    assert len(result.passing) == 4
    assert [r.specialist_slug for r in result.passing] == [
        "dev-wrapper",
        "lad-wrapper",
        "qa",
        "review-bmad-wrapper",
    ]
    assert result.cross_reference_violation == []


# ---------------------------------------------------------------------------
# Rule 1 (path-form) cases
# ---------------------------------------------------------------------------


def test_rule1_path_form_basic_violation(tmp_path: pathlib.Path) -> None:
    """qa.md contains literal `agents/dev-wrapper.md` → exit 1."""
    agents_dir = _make_agents_dir(
        tmp_path,
        specialists={
            "dev-wrapper.md": "# Dev\n",
            "qa.md": "# QA\nSee agents/dev-wrapper.md for details.\n",
        },
    )
    rc, out, _ = _capture_main(["--agents-dir", str(agents_dir)])
    assert rc == 1
    assert "Pluggability violation:" in out
    assert "qa.md" in out
    assert "specialist qa" in out
    assert "specialist dev-wrapper" in out
    assert "via rule path-form" in out
    assert 'matched "agents/dev-wrapper.md"' in out
    assert "at line 2" in out


def test_rule1_path_form_inside_markdown_link(tmp_path: pathlib.Path) -> None:
    """Match inside a markdown link [text](agents/<other>.md) → fires."""
    agents_dir = _make_agents_dir(
        tmp_path,
        specialists={
            "dev-wrapper.md": "# Dev\n",
            "qa.md": (
                "# QA\nSee [the dev wrapper](agents/dev-wrapper.md) for details.\n"
            ),
        },
    )
    result = run_pluggability_gate(agents_dir)
    assert len(result.cross_reference_violation) == 1
    finding = result.cross_reference_violation[0]
    assert finding.offending_specialist == "qa"
    assert finding.referenced_specialist == "dev-wrapper"
    assert finding.rule == "path-form"
    assert finding.matched_text == "agents/dev-wrapper.md"


def test_rule1_path_form_no_match_substring_superset(
    tmp_path: pathlib.Path,
) -> None:
    """`agents/dev-wrapper.mds` — trailing `s` is word char, NO boundary.

    Per Python's ``re`` ``\\b`` semantics: a position between a word char
    and a non-word char. The position after `.md` in ``.mds`` is between
    `d` (word) and `s` (word) — no boundary, no match. This test pins
    the desired posture: file paths embedded in unrelated identifier-
    shaped strings (``...mds``) do NOT match; file paths bounded by
    sentence punctuation, brackets, or whitespace DO match (covered by
    other tests in this module).
    """
    agents_dir = _make_agents_dir(
        tmp_path,
        specialists={
            "dev-wrapper.md": "# Dev\n",
            "qa.md": "# QA\nReference: agents/dev-wrapper.mds (NOT a real path).\n",
        },
    )
    result = run_pluggability_gate(agents_dir)
    assert result.cross_reference_violation == []
    # Both specialists pass cleanly.
    assert len(result.passing) == 2


def test_rule1_path_form_self_reference_excluded(
    tmp_path: pathlib.Path,
) -> None:
    """A specialist may name its own path; self-reference is not cross-ref."""
    agents_dir = _make_agents_dir(
        tmp_path,
        specialists={
            "dev-wrapper.md": (
                "# Dev Wrapper (agents/dev-wrapper.md)\nMy own path is fine.\n"
            ),
            "qa.md": "# QA\nNo references.\n",
        },
    )
    result = run_pluggability_gate(agents_dir)
    assert result.cross_reference_violation == []
    assert len(result.passing) == 2


def test_rule1_path_form_no_match_bak_extension(tmp_path: pathlib.Path) -> None:
    """`agents/dev-wrapper.md.bak` — trailing `.` in negative-lookahead; NO match.

    Documents the D2 fix: Rule 1 uses ``(?!\\w|[.]\\w)`` (negative
    lookahead) rather than ``\\b`` so filenames with extension-like
    suffixes (dot followed by a word char) do not trigger. ``\\b``
    would fire between the word-char ``d`` and non-word-char ``.``,
    causing a false positive; ``(?!\\w|[.]\\w)`` correctly suppresses
    it while still matching ``agents/dev-wrapper.md.`` at end-of-sentence
    (the sentence ``.`` is not followed by a word char).
    """
    agents_dir = _make_agents_dir(
        tmp_path,
        specialists={
            "dev-wrapper.md": "# Dev\n",
            "qa.md": (
                "# QA\nOld backup reference: agents/dev-wrapper.md.bak "
                "(not a real path).\n"
            ),
        },
    )
    result = run_pluggability_gate(agents_dir)
    assert result.cross_reference_violation == []
    assert len(result.passing) == 2


# ---------------------------------------------------------------------------
# Rule 2 (slug-form) cases
# ---------------------------------------------------------------------------


def test_rule2_slug_form_basic_violation(tmp_path: pathlib.Path) -> None:
    """qa.md contains bare token `dev-wrapper` → exit 1."""
    agents_dir = _make_agents_dir(
        tmp_path,
        specialists={
            "dev-wrapper.md": "# Dev\n",
            "qa.md": "# QA\nConsume the dev-wrapper's envelope.\n",
        },
    )
    rc, out, _ = _capture_main(["--agents-dir", str(agents_dir)])
    assert rc == 1
    assert "Pluggability violation:" in out
    assert "specialist qa" in out
    assert "specialist dev-wrapper" in out
    assert "via rule slug-form" in out
    assert 'matched "dev-wrapper"' in out


def test_rule2_slug_form_multiple_matches_per_file(
    tmp_path: pathlib.Path,
) -> None:
    """Two distinct lines mentioning `dev-wrapper` → 2 findings."""
    agents_dir = _make_agents_dir(
        tmp_path,
        specialists={
            "dev-wrapper.md": "# Dev\n",
            "qa.md": (
                "# QA\n"
                "First mention: dev-wrapper handles Dev seam.\n"
                "Second mention: dev-wrapper emits envelope.\n"
            ),
        },
    )
    result = run_pluggability_gate(agents_dir)
    assert len(result.cross_reference_violation) == 2
    line_numbers = sorted(
        f.line_number for f in result.cross_reference_violation
    )
    assert line_numbers == [2, 3]
    for f in result.cross_reference_violation:
        assert f.rule == "slug-form"
        assert f.offending_specialist == "qa"
        assert f.referenced_specialist == "dev-wrapper"


def test_rule2_slug_form_single_word_slug_qa_excluded(
    tmp_path: pathlib.Path,
) -> None:
    """Bare token `qa` in dev-wrapper.md → NO match (deliberate asymmetry).

    Per AC-4: the slug `qa` is a single-word slug, NOT in the multi-hyphen
    set, so Rule 2 does not fire. Path-form Rule 1 is the ONLY mechanism
    that catches QA cross-references — a specialist referencing `qa` as
    a bare token is NOT flagged. This is a feature, not a bug — single-
    word tokens collide with marker classes (``qa-failed``), lifecycle
    states (``backlog → … → qa → done``), section names (``## QA Behavioral
    Plan``), envelope fields (``qa_results``), and free-text references.
    """
    agents_dir = _make_agents_dir(
        tmp_path,
        specialists={
            "dev-wrapper.md": (
                "# Dev\n"
                "Lifecycle includes qa state and the qa-failed marker.\n"
            ),
            "qa.md": "# QA\n",
        },
    )
    result = run_pluggability_gate(agents_dir)
    assert result.cross_reference_violation == []
    assert len(result.passing) == 2


def test_rule2_slug_form_kebab_extension_matches(
    tmp_path: pathlib.Path,
) -> None:
    """`dev-wrapper-helper-thing` — `-` is non-word, boundary fires, match.

    Rule 2's ``\\b`` semantics treat ``-`` as a word boundary, so any
    kebab-case-extension of a specialist slug DOES match. Desirable: it
    means ``dev-wrapper-foo``-style helper names that namespace under a
    specialist's slug are NOT permitted to be defined inside another
    specialist's file.
    """
    agents_dir = _make_agents_dir(
        tmp_path,
        specialists={
            "dev-wrapper.md": "# Dev\n",
            "qa.md": "# QA\nReferences dev-wrapper-helper-thing internally.\n",
        },
    )
    result = run_pluggability_gate(agents_dir)
    assert len(result.cross_reference_violation) == 1
    finding = result.cross_reference_violation[0]
    assert finding.rule == "slug-form"
    assert finding.matched_text == "dev-wrapper"


def test_rule2_slug_form_concatenated_no_match(tmp_path: pathlib.Path) -> None:
    """`dev-wrapperthing` — `r` followed by `t`, both word chars, no boundary."""
    agents_dir = _make_agents_dir(
        tmp_path,
        specialists={
            "dev-wrapper.md": "# Dev\n",
            "qa.md": "# QA\nThe dev-wrapperthing variable lives elsewhere.\n",
        },
    )
    result = run_pluggability_gate(agents_dir)
    assert result.cross_reference_violation == []


def test_rule2_slug_form_self_reference_excluded(
    tmp_path: pathlib.Path,
) -> None:
    """A specialist may name its own slug; self-reference is not cross-ref."""
    agents_dir = _make_agents_dir(
        tmp_path,
        specialists={
            "dev-wrapper.md": "# Dev Wrapper\nThe dev-wrapper subagent.\n",
            "qa.md": "# QA\n",
        },
    )
    result = run_pluggability_gate(agents_dir)
    assert result.cross_reference_violation == []
    assert len(result.passing) == 2


def test_rule2_slug_form_not_suppressed_in_superstring_prefix(
    tmp_path: pathlib.Path,
) -> None:
    """`myagents/dev-wrapper` — `agents/` preceded by `y` (word char); NOT suppressed.

    Documents the P2 fix: path-prefix suppression checks that the
    ``agents/`` literal is at a word boundary. If ``agents/`` is the
    suffix of a longer identifier (``myagents/``), the preceding char
    is a word char and suppression must NOT fire — ``dev-wrapper`` is a
    genuine Rule 2 cross-reference.
    """
    agents_dir = _make_agents_dir(
        tmp_path,
        specialists={
            "dev-wrapper.md": "# Dev\n",
            "qa.md": (
                "# QA\nConsult myagents/dev-wrapper for the alternate path.\n"
            ),
        },
    )
    result = run_pluggability_gate(agents_dir)
    assert len(result.cross_reference_violation) == 1
    finding = result.cross_reference_violation[0]
    assert finding.rule == "slug-form"
    assert finding.matched_text == "dev-wrapper"
    assert finding.offending_specialist == "qa"


# ---------------------------------------------------------------------------
# Permitted-reference cases (allowlist enforced by construction)
# ---------------------------------------------------------------------------


def test_permitted_substrate_path_no_violation(tmp_path: pathlib.Path) -> None:
    """tools/loud-fail-harness/... reference → not under agents/, no fire."""
    agents_dir = _make_agents_dir(
        tmp_path,
        specialists={
            "dev-wrapper.md": (
                "# Dev\n"
                "Validates via tools/loud-fail-harness/src/loud_fail_harness/"
                "envelope_validator.py.\n"
            ),
        },
    )
    result = run_pluggability_gate(agents_dir)
    assert result.cross_reference_violation == []
    assert len(result.passing) == 1


def test_permitted_schema_path_no_violation(tmp_path: pathlib.Path) -> None:
    """schemas/<name>.yaml reference → not under agents/, no fire."""
    agents_dir = _make_agents_dir(
        tmp_path,
        specialists={
            "dev-wrapper.md": "# Dev\nReads schemas/envelope.schema.yaml.\n",
        },
    )
    result = run_pluggability_gate(agents_dir)
    assert result.cross_reference_violation == []
    assert len(result.passing) == 1


def test_permitted_bmad_core_skill_no_violation(
    tmp_path: pathlib.Path,
) -> None:
    """`bmad-dev-story` is NOT a discovered specialist; Rule 2 doesn't iter."""
    agents_dir = _make_agents_dir(
        tmp_path,
        specialists={
            "dev-wrapper.md": (
                "# Dev\nWraps bmad-dev-story (BMAD-core skill per FR40).\n"
            ),
        },
    )
    result = run_pluggability_gate(agents_dir)
    assert result.cross_reference_violation == []


def test_permitted_marker_class_qa_prefix_no_violation(
    tmp_path: pathlib.Path,
) -> None:
    """`qa-failed` marker class → `qa` not in multi-hyphen set; no fire."""
    agents_dir = _make_agents_dir(
        tmp_path,
        specialists={
            "dev-wrapper.md": "# Dev\nEmits qa-failed marker on retry.\n",
            "qa.md": "# QA\n",
        },
    )
    result = run_pluggability_gate(agents_dir)
    assert result.cross_reference_violation == []


def test_permitted_section_name_qa_behavioral_plan_no_violation(
    tmp_path: pathlib.Path,
) -> None:
    """`## QA Behavioral Plan` — PascalCase QA is not a slug; no fire."""
    agents_dir = _make_agents_dir(
        tmp_path,
        specialists={
            "dev-wrapper.md": "# Dev\n## QA Behavioral Plan\nSection.\n",
            "qa.md": "# QA\n",
        },
    )
    result = run_pluggability_gate(agents_dir)
    assert result.cross_reference_violation == []


def test_permitted_lifecycle_state_qa_no_violation(
    tmp_path: pathlib.Path,
) -> None:
    """Lifecycle state `qa` in YAML-ish context → single-word slug; no fire."""
    agents_dir = _make_agents_dir(
        tmp_path,
        specialists={
            "dev-wrapper.md": "# Dev\nstatus: qa\n",
            "qa.md": "# QA\n",
        },
    )
    result = run_pluggability_gate(agents_dir)
    assert result.cross_reference_violation == []


def test_permitted_agent_file_as_data_placeholder_no_violation(
    tmp_path: pathlib.Path,
) -> None:
    """Free-text `agents/<X>.md` placeholder → not a literal slug; no fire."""
    agents_dir = _make_agents_dir(
        tmp_path,
        specialists={
            "dev-wrapper.md": (
                "# Dev\n"
                "The dispatch wrapper reads agents/<X>.md as data.\n"
            ),
            "qa.md": "# QA\n",
        },
    )
    result = run_pluggability_gate(agents_dir)
    assert result.cross_reference_violation == []


# ---------------------------------------------------------------------------
# Mixed cases
# ---------------------------------------------------------------------------


def test_mixed_passing_and_violation_in_same_run(
    tmp_path: pathlib.Path,
) -> None:
    """One clean specialist + one offending specialist → 1 passing, 1 finding.

    The ``dev-wrapper`` specialist appears in ``passing``; the ``qa``
    specialist appears ONLY in violations, NOT in passing.
    """
    agents_dir = _make_agents_dir(
        tmp_path,
        specialists={
            "dev-wrapper.md": "# Dev\nClean specialist.\n",
            "qa.md": "# QA\nReferences agents/dev-wrapper.md.\n",
        },
    )
    rc, out, _ = _capture_main(["--agents-dir", str(agents_dir)])
    assert rc == 1
    result = run_pluggability_gate(agents_dir)
    assert [r.specialist_slug for r in result.passing] == ["dev-wrapper"]
    assert len(result.cross_reference_violation) == 1
    assert result.cross_reference_violation[0].offending_specialist == "qa"
    # qa is NOT in passing.
    assert "qa" not in [r.specialist_slug for r in result.passing]
    assert "1 passing specialist(s)" in out
    assert "1 cross-reference violation(s)" in out
    assert "across 1 specialist file(s)" in out


def test_both_rules_fire_on_same_offending_file(
    tmp_path: pathlib.Path,
) -> None:
    """Three specialists; qa.md has 1 Rule 1 + 1 Rule 2 finding → 2 findings."""
    agents_dir = _make_agents_dir(
        tmp_path,
        specialists={
            "dev-wrapper.md": "# Dev\n",
            "lad-wrapper.md": "# LAD\n",
            "qa.md": (
                "# QA\n"
                "Path-form: agents/dev-wrapper.md.\n"
                "Slug-form: lad-wrapper handles external review.\n"
            ),
        },
    )
    result = run_pluggability_gate(agents_dir)
    assert len(result.cross_reference_violation) == 2
    rules = {f.rule for f in result.cross_reference_violation}
    assert rules == {"path-form", "slug-form"}
    referenced = {
        f.referenced_specialist for f in result.cross_reference_violation
    }
    assert referenced == {"dev-wrapper", "lad-wrapper"}


# ---------------------------------------------------------------------------
# Discovery edge cases
# ---------------------------------------------------------------------------


def test_subdirectory_specialist_not_discovered(tmp_path: pathlib.Path) -> None:
    """agents/subdir/foo.md is NOT discovered (top-level glob only).

    Documents the do-not-do row "do not extend the specialist set by
    hiding files in subdirectories".
    """
    agents_dir = _make_agents_dir(
        tmp_path,
        specialists={"subdir/foo.md": "# Hidden\n"},
    )
    discovered = discover_specialists(agents_dir)
    assert discovered == []
    rc, out, _ = _capture_main(["--agents-dir", str(agents_dir)])
    assert rc == 0
    assert "0 passing specialist(s)" in out


def test_non_md_file_ignored(tmp_path: pathlib.Path) -> None:
    """Non-`.md` files are silently ignored (top-level glob filters by suffix)."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "README.txt").write_text("README\n", encoding="utf-8")
    _write_specialist(agents_dir / "dev-wrapper.md", body="# Dev\n")
    result = run_pluggability_gate(agents_dir)
    assert [r.file_name for r in result.passing] == ["dev-wrapper.md"]


def test_non_md_file_with_md_substring_ignored(tmp_path: pathlib.Path) -> None:
    """`*.md` is exact-suffix; `foo.markdown` is NOT discovered."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    _write_specialist(agents_dir / "foo.markdown", body="# Markdown\n")
    _write_specialist(agents_dir / "dev-wrapper.md", body="# Dev\n")
    discovered = discover_specialists(agents_dir)
    assert [p.name for p in discovered] == ["dev-wrapper.md"]


def test_empty_file_zero_bytes(tmp_path: pathlib.Path) -> None:
    """Empty (0-byte) specialist file → 0 scanned lines; passes cleanly."""
    agents_dir = _make_agents_dir(tmp_path, specialists={"foo.md": ""})
    result = run_pluggability_gate(agents_dir)
    assert len(result.passing) == 1
    assert result.passing[0].scanned_line_count == 0


# ---------------------------------------------------------------------------
# Loud-fail / harness-level errors (Pattern 5)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    sys.platform == "win32" or (hasattr(os, "getuid") and os.getuid() == 0),
    reason="chmod 000 doesn't deny read on Windows or when running as root",
)
def test_loud_fail_on_unreadable_file(tmp_path: pathlib.Path) -> None:
    """A `.md` file with chmod 000 → exit 2 with named stderr message."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    target = agents_dir / "dev-wrapper.md"
    _write_specialist(target, body="# Dev\n")
    os.chmod(target, 0o000)
    try:
        rc, _, err = _capture_main(["--agents-dir", str(agents_dir)])
    finally:
        os.chmod(target, 0o644)
    assert rc == 2
    assert "harness-level error: agent file unreadable" in err
    assert str(target) in err


def test_loud_fail_on_non_utf8_file(tmp_path: pathlib.Path) -> None:
    """Non-UTF-8 bytes in a `.md` file → exit 2 with named stderr message."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    target = agents_dir / "dev-wrapper.md"
    target.write_bytes(b"\xff\xfe\x00invalid")
    rc, _, err = _capture_main(["--agents-dir", str(agents_dir)])
    assert rc == 2
    assert "harness-level error: agent file not UTF-8" in err
    assert str(target) in err


@pytest.mark.skipif(
    sys.platform == "win32" or (hasattr(os, "getuid") and os.getuid() == 0),
    reason="chmod 000 doesn't deny read on Windows or when running as root",
)
def test_loud_fail_on_unreadable_agents_dir(tmp_path: pathlib.Path) -> None:
    """agents/ with chmod 000 → exit 2 with `agents/ directory unreadable`."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    _write_specialist(agents_dir / "dev-wrapper.md", body="# Dev\n")
    os.chmod(agents_dir, 0o000)
    try:
        rc, _, err = _capture_main(["--agents-dir", str(agents_dir)])
    finally:
        os.chmod(agents_dir, 0o755)
    assert rc == 2
    assert "harness-level error: agents/ directory unreadable" in err


# ---------------------------------------------------------------------------
# Determinism + serialization
# ---------------------------------------------------------------------------


def test_determinism_repeated_invocation(tmp_path: pathlib.Path) -> None:
    """Two invocations on the same input produce identical results."""
    agents_dir = _make_agents_dir(
        tmp_path,
        specialists={
            "dev-wrapper.md": "# Dev\n",
            "review-bmad-wrapper.md": "# Review\nUses dev-wrapper internally.\n",
            "qa.md": (
                "# QA\n"
                "References agents/dev-wrapper.md.\n"
                "Also lad-wrapper integration.\n"
            ),
            "lad-wrapper.md": "# LAD\n",
        },
    )
    first = run_pluggability_gate(agents_dir)
    second = run_pluggability_gate(agents_dir)
    assert first == second


def test_gate_result_json_serialization_stable(tmp_path: pathlib.Path) -> None:
    """``model_dump_json()`` is byte-identical across runs on the same input."""
    agents_dir = _make_agents_dir(
        tmp_path,
        specialists={
            "dev-wrapper.md": "# Dev\n",
            "qa.md": "# QA\nReferences agents/dev-wrapper.md and dev-wrapper.\n",
        },
    )
    result = run_pluggability_gate(agents_dir)
    assert len(result.cross_reference_violation) == 2
    rules = {f.rule for f in result.cross_reference_violation}
    assert "path-form" in rules
    assert "slug-form" in rules
    first = result.model_dump_json()
    second = run_pluggability_gate(agents_dir).model_dump_json()
    assert first == second
    # Sanity-check field order in the serialized form (load-bearing for
    # determinism per AC-5).
    passing_idx = first.index('"passing"')
    violation_idx = first.index('"cross_reference_violation"')
    assert passing_idx < violation_idx


# ---------------------------------------------------------------------------
# Pydantic v2 frozen-model discipline
# ---------------------------------------------------------------------------


def test_reference_is_frozen_and_hashable() -> None:
    ref = Reference(
        specialist_slug="dev-wrapper",
        file_name="dev-wrapper.md",
        scanned_line_count=10,
    )
    with pytest.raises(ValidationError):
        ref.specialist_slug = "qa"  # type: ignore[misc]
    assert hash(ref) == hash(
        Reference(
            specialist_slug="dev-wrapper",
            file_name="dev-wrapper.md",
            scanned_line_count=10,
        )
    )


def test_cross_reference_finding_is_frozen_and_hashable() -> None:
    finding = CrossReferenceFinding(
        offending_file="qa.md",
        offending_specialist="qa",
        referenced_specialist="dev-wrapper",
        matched_text="agents/dev-wrapper.md",
        line_number=2,
        rule="path-form",
    )
    with pytest.raises(ValidationError):
        finding.line_number = 3  # type: ignore[misc]
    assert hash(finding) == hash(
        CrossReferenceFinding(
            offending_file="qa.md",
            offending_specialist="qa",
            referenced_specialist="dev-wrapper",
            matched_text="agents/dev-wrapper.md",
            line_number=2,
            rule="path-form",
        )
    )


def test_gate_result_frozen_not_hashable() -> None:
    """GateResult is frozen (assignment raises) but NOT hashable (list fields)."""
    result = GateResult(passing=[], cross_reference_violation=[])
    with pytest.raises(ValidationError):
        result.passing = [  # type: ignore[misc]
            Reference(
                specialist_slug="x",
                file_name="x.md",
                scanned_line_count=1,
            )
        ]
    with pytest.raises(TypeError):
        hash(result)


# ---------------------------------------------------------------------------
# CLI / main exit-code matrix
# ---------------------------------------------------------------------------


def test_canonical_corpus_baseline_zero() -> None:
    """At story 1.10a's landing time the canonical agents/ dir does NOT exist.

    This test asserts the gate's CORRECT POSTURE at landing time. Once
    stories 2.8 / 2.9 / 2.10 / 4.x land specialist files, this test's
    expected Summary line shifts to reflect the discovered set. The
    canonical agents/ may already exist (a dev experimenting locally)
    but at this story's landing it's expected to be absent — both
    branches are exit 0.
    """
    rc, out, err = _capture_main([])
    assert rc == 0, f"stdout: {out}\nstderr: {err}"
    # Whatever the discovered count, no cross-references should exist on
    # main at this story's landing time.
    assert "0 cross-reference violation(s)" in out


def test_main_help_resolves(capsys: pytest.CaptureFixture[str]) -> None:
    """``main(['--help'])`` raises SystemExit(0) and prints expected help text."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "--agents-dir" in captured.out
    # AC-9 row "main --help" requires the help text mentions Rule 1 + Rule 2
    # by name OR points to the module docstring's rule documentation.
    assert "Rule 1" in captured.out
    assert "Rule 2" in captured.out


def test_main_with_custom_agents_dir(tmp_path: pathlib.Path) -> None:
    """``main(['--agents-dir', X])`` uses the custom path, not ``find_repo_root``."""
    agents_dir = _make_agents_dir(
        tmp_path,
        specialists={"dev-wrapper.md": "# Dev\n"},
    )
    rc, out, _ = _capture_main(["--agents-dir", str(agents_dir)])
    assert rc == 0
    assert "1 passing specialist(s)" in out


# ---------------------------------------------------------------------------
# Diagnostic-prose verbatim (AC-7)
# ---------------------------------------------------------------------------


def test_format_findings_matches_ac7_verbatim(tmp_path: pathlib.Path) -> None:
    """``format_findings`` output matches AC-7 finding shape, remediation, summary.

    For one violation, asserts the AC-7 row-1 finding diagnostic substring
    AND the remediation-pointer substring AND the AC-7 Summary footer
    line — verbatim, to prevent inadvertent prose drift.
    """
    agents_dir = _make_agents_dir(
        tmp_path,
        specialists={
            "dev-wrapper.md": "# Dev\n",
            "qa.md": "# QA\nSee agents/dev-wrapper.md.\n",
        },
    )
    rc, out, _ = _capture_main(["--agents-dir", str(agents_dir)])
    assert rc == 1

    # AC-7 Header (first 3 lines).
    assert "Pluggability gate (story 1.10a; FR62)" in out
    assert "  agents dir: " in out
    assert (
        "  rules: Rule 1 (path-form: agents/<other>.md) + Rule 2 "
        "(slug-form: multi-hyphen specialist slugs only)"
    ) in out

    # AC-7 finding diagnostic (verbatim shape).
    assert (
        "Pluggability violation: qa.md (specialist qa) cross-references "
        "specialist dev-wrapper via rule path-form: matched "
        '"agents/dev-wrapper.md" at line 2.'
    ) in out

    # AC-7 remediation pointer (verbatim substring).
    assert (
        "(per FR62 + ADR-002 cell-1 invariant: specialist-to-specialist "
        "references break pluggability"
    ) in out
    assert "Remediation: (a) remove the reference" in out
    assert "story 2.2's atomic-write helper" in out
    assert "epics.md story 2.6" in out

    # AC-7 Summary footer (verbatim).
    assert (
        "Summary: 1 passing specialist(s), 1 cross-reference violation(s) "
        "across 1 specialist file(s)."
    ) in out


# ---------------------------------------------------------------------------
# Discover-specialists fine-grained unit tests (AC-2 directly)
# ---------------------------------------------------------------------------


def test_discover_specialists_returns_empty_for_missing_dir(
    tmp_path: pathlib.Path,
) -> None:
    """Missing dir → []; this is the loud-fail-correct response, not a raise."""
    missing = tmp_path / "nonexistent"
    assert discover_specialists(missing) == []


def test_discover_specialists_sorts_lexicographically(
    tmp_path: pathlib.Path,
) -> None:
    agents_dir = _make_agents_dir(
        tmp_path,
        specialists={
            "z.md": "# z\n",
            "a.md": "# a\n",
            "m.md": "# m\n",
        },
    )
    discovered = discover_specialists(agents_dir)
    assert [p.name for p in discovered] == ["a.md", "m.md", "z.md"]


# ---------------------------------------------------------------------------
# find_cross_references_path_form / find_cross_references_slug_form direct
# unit tests (AC-3 / AC-4 directly — fine-grained vs. CLI tests)
# ---------------------------------------------------------------------------


def test_find_cross_references_path_form_skips_self(
    tmp_path: pathlib.Path,
) -> None:
    """When `other.name == file_path.name`, no finding is emitted."""
    file_path = tmp_path / "agents" / "dev-wrapper.md"
    findings = find_cross_references_path_form(
        file_path,
        "agents/dev-wrapper.md is my own path",
        [file_path],
    )
    assert findings == []


def test_find_cross_references_slug_form_skips_single_word_slug(
    tmp_path: pathlib.Path,
) -> None:
    """Single-word slug never produces a finding (no hyphen → skip)."""
    file_path = tmp_path / "agents" / "dev-wrapper.md"
    other = tmp_path / "agents" / "qa.md"
    findings = find_cross_references_slug_form(
        file_path,
        "the qa specialist runs after dev",
        [file_path, other],
    )
    assert findings == []
