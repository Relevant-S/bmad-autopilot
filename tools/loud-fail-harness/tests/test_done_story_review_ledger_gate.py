"""Non-vacuous fixture corpus for the done-story review-ledger gate (Story 24.3).

Drives the gate end-to-end over ``tmp_path`` sprint-status + story-doc sets,
proving it is not green-on-empty.

AC-8 — fixture corpus:
    [x] test_clean_done_story_all_checked_exits_zero
    [x] test_unchecked_patch_emits_unchecked_review_finding
    [x] test_unchecked_decision_emits_unchecked_review_finding
    [x] test_unchecked_defer_emits_unchecked_review_finding (R1 dominates)
    [x] test_checked_defer_without_pointer_emits_deferred_finding_missing_pointer
    [x] test_done_story_with_no_doc_emits_done_story_doc_unresolvable
    [x] test_non_done_story_with_unchecked_items_exits_zero (status-gating)
    [x] test_fenced_and_inline_prose_unchecked_text_exits_zero (fence/scope)
    [x] test_findings_are_byte_stable_ordered

AC-7 — CLI + harness-level error:
    [x] test_main_exit_two_when_sprint_status_unresolvable
    [x] test_main_exit_two_when_artifacts_dir_missing
    [x] test_main_exit_two_on_malformed_sprint_status
    [x] test_artifacts_dir_defaults_to_sprint_status_parent
"""

from __future__ import annotations

import pathlib

from loud_fail_harness.done_story_review_ledger_gate import (
    evaluate_done_story_ledgers,
    main,
    run_done_story_review_ledger_gate,
)


def _write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _sprint_status(**statuses: str) -> str:
    lines = ["development_status:"]
    lines.extend(f"  {key}: {value}" for key, value in statuses.items())
    return "\n".join(lines) + "\n"


def _run(
    tmp_path: pathlib.Path, sprint_status_text: str, docs: dict[str, str]
) -> object:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    _write(tmp_path / "sprint-status.yaml", sprint_status_text)
    for story_key, body in docs.items():
        _write(artifacts / f"{story_key}.md", body)
    text = (tmp_path / "sprint-status.yaml").read_text(encoding="utf-8")
    from loud_fail_harness.done_story_review_ledger import iter_done_story_keys

    return evaluate_done_story_ledgers(
        done_story_keys=iter_done_story_keys(text), artifacts_dir=artifacts
    )


_CLEAN_DOC = """\
### Review Findings

- [x] [Review][Patch] resolved fix
- [x] [Review][Decision] decided
- [x] [Review][Defer] deferred to deferred-work.md:42
"""


def test_clean_done_story_all_checked_exits_zero(tmp_path: pathlib.Path) -> None:
    result = _run(
        tmp_path,
        _sprint_status(**{"9-1-clean": "done"}),
        {"9-1-clean": _CLEAN_DOC},
    )
    assert result.findings == ()


def test_unchecked_patch_emits_unchecked_review_finding(
    tmp_path: pathlib.Path,
) -> None:
    result = _run(
        tmp_path,
        _sprint_status(**{"3-1-x": "done"}),
        {"3-1-x": "### Review Findings\n\n- [ ] [Review][Patch] open fix\n"},
    )
    assert [f.rule for f in result.findings] == ["unchecked-review-finding"]
    assert result.findings[0].story_key == "3-1-x"


def test_unchecked_decision_emits_unchecked_review_finding(
    tmp_path: pathlib.Path,
) -> None:
    result = _run(
        tmp_path,
        _sprint_status(**{"3-2-x": "done"}),
        {"3-2-x": "### Review Findings\n\n- [ ] [Review][Decision] open\n"},
    )
    assert [f.rule for f in result.findings] == ["unchecked-review-finding"]


def test_unchecked_defer_emits_unchecked_review_finding(
    tmp_path: pathlib.Path,
) -> None:
    # Unchecked dominates: R1 fires regardless of tag (incl. Defer).
    result = _run(
        tmp_path,
        _sprint_status(**{"5-7-x": "done"}),
        {"5-7-x": "### Review Findings\n\n- [ ] [Review][Defer] open defer\n"},
    )
    assert [f.rule for f in result.findings] == ["unchecked-review-finding"]


def test_checked_defer_without_pointer_emits_deferred_finding_missing_pointer(
    tmp_path: pathlib.Path,
) -> None:
    result = _run(
        tmp_path,
        _sprint_status(**{"7-1-x": "done"}),
        {"7-1-x": "### Review Findings\n\n- [x] [Review][Defer] no pointer here\n"},
    )
    assert [f.rule for f in result.findings] == ["deferred-finding-missing-pointer"]


def test_done_story_with_no_doc_emits_done_story_doc_unresolvable(
    tmp_path: pathlib.Path,
) -> None:
    result = _run(tmp_path, _sprint_status(**{"10-4-ghost": "done"}), {})
    assert [f.rule for f in result.findings] == ["done-story-doc-unresolvable"]
    assert result.findings[0].line_number == 0


def test_non_done_story_with_unchecked_items_exits_zero(
    tmp_path: pathlib.Path,
) -> None:
    # Status-gating: a `review` story with unchecked items is NOT a violation.
    result = _run(
        tmp_path,
        _sprint_status(**{"4-1-inflight": "review"}),
        {"4-1-inflight": "### Review Findings\n\n- [ ] [Review][Patch] open\n"},
    )
    assert result.findings == ()


def test_fenced_and_inline_prose_unchecked_text_exits_zero(
    tmp_path: pathlib.Path,
) -> None:
    doc = (
        "### Review Findings\n\n"
        "```\n- [ ] [Review][Patch] fenced example\n```\n\n"
        "Inline `[ ][Review][Patch]` prose is normal narrative.\n"
    )
    result = _run(tmp_path, _sprint_status(**{"5-1-x": "done"}), {"5-1-x": doc})
    assert result.findings == ()


def test_findings_are_byte_stable_ordered(tmp_path: pathlib.Path) -> None:
    doc = (
        "### Review Findings\n\n"
        "- [ ] [Review][Decision] second by line\n"
        "- [ ] [Review][Patch] third by line\n"
    )
    result = _run(
        tmp_path,
        _sprint_status(**{"6-2-b": "done", "1-1-a": "done"}),
        {
            "6-2-b": doc,
            "1-1-a": "### Review Findings\n\n- [ ] [Review][Patch] open\n",
        },
    )
    keys = [(f.story_key, f.line_number, f.rule) for f in result.findings]
    assert keys == sorted(keys)
    # story_key sorts before line_number: 1-1-a precedes 6-2-b.
    assert result.findings[0].story_key == "1-1-a"


# --------------------------------------------------------------------------- #
# CLI + harness-level error paths (AC-7)                                       #
# --------------------------------------------------------------------------- #


def test_main_exit_two_when_sprint_status_unresolvable(
    tmp_path: pathlib.Path,
) -> None:
    code = main(["--sprint-status", str(tmp_path / "nope.yaml")])
    assert code == 2


def test_main_exit_two_when_artifacts_dir_missing(tmp_path: pathlib.Path) -> None:
    sprint = tmp_path / "sprint-status.yaml"
    sprint.write_text(_sprint_status(**{"1-1-x": "done"}), encoding="utf-8")
    code = main(
        [
            "--sprint-status",
            str(sprint),
            "--artifacts-dir",
            str(tmp_path / "missing"),
        ]
    )
    assert code == 2


def test_main_exit_two_on_malformed_sprint_status(tmp_path: pathlib.Path) -> None:
    sprint = tmp_path / "sprint-status.yaml"
    sprint.write_text("development_status:\n  - [unbalanced\n", encoding="utf-8")
    code = main(["--sprint-status", str(sprint), "--artifacts-dir", str(tmp_path)])
    assert code == 2


def test_main_exits_one_on_finding(tmp_path: pathlib.Path) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "3-1-x.md").write_text(
        "### Review Findings\n\n- [ ] [Review][Patch] open\n", encoding="utf-8"
    )
    sprint = tmp_path / "sprint-status.yaml"
    sprint.write_text(_sprint_status(**{"3-1-x": "done"}), encoding="utf-8")
    code = main(
        ["--sprint-status", str(sprint), "--artifacts-dir", str(artifacts)]
    )
    assert code == 1


def test_main_exits_zero_on_clean(tmp_path: pathlib.Path) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "9-1-clean.md").write_text(_CLEAN_DOC, encoding="utf-8")
    sprint = tmp_path / "sprint-status.yaml"
    sprint.write_text(_sprint_status(**{"9-1-clean": "done"}), encoding="utf-8")
    code = main(
        ["--sprint-status", str(sprint), "--artifacts-dir", str(artifacts)]
    )
    assert code == 0


def test_artifacts_dir_defaults_to_sprint_status_parent(
    tmp_path: pathlib.Path,
) -> None:
    # When --artifacts-dir is omitted, docs are resolved next to sprint-status.
    sprint = tmp_path / "sprint-status.yaml"
    sprint.write_text(_sprint_status(**{"9-1-clean": "done"}), encoding="utf-8")
    (tmp_path / "9-1-clean.md").write_text(_CLEAN_DOC, encoding="utf-8")
    code = main(["--sprint-status", str(sprint)])
    assert code == 0


def test_run_gate_orchestrates_read_enumerate_evaluate(
    tmp_path: pathlib.Path,
) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "3-1-x.md").write_text(
        "### Review Findings\n\n- [ ] [Review][Patch] open\n", encoding="utf-8"
    )
    sprint = tmp_path / "sprint-status.yaml"
    sprint.write_text(_sprint_status(**{"3-1-x": "done"}), encoding="utf-8")
    result = run_done_story_review_ledger_gate(
        sprint_status_path=sprint, artifacts_dir=artifacts
    )
    assert result.done_stories_scanned == ("3-1-x",)
    assert len(result.findings) == 1


# --------------------------------------------------------------------------- #
# Boundary witnesses (AC-10) — build-time gate, NO runtime marker             #
# --------------------------------------------------------------------------- #


def test_new_modules_emit_no_runtime_marker() -> None:
    # Build-time gate (contrast 24.1's runtime marker): the two new modules
    # must not touch the active_markers surface, name a marker class, or load
    # the marker taxonomy. Keeps the closed-set at 34 / schema_version "1.12".
    src = (
        pathlib.Path(__file__).resolve().parents[1]
        / "src"
        / "loud_fail_harness"
    )
    for stem in ("done_story_review_ledger", "done_story_review_ledger_gate"):
        text = (src / f"{stem}.py").read_text(encoding="utf-8")
        assert "active_markers" not in text
        assert "marker_class=" not in text
        assert "marker-taxonomy" not in text
