"""Non-vacuous fixture corpus for the forward-pointer-drift gate (Story 22.4).

Drives the gate end-to-end over ``tmp_path`` carry-surface + sprint-status
sets, proving it catches the precise failure it exists to catch (a still-
pending pointer binding a ``done`` target) and is not green-on-empty.

AC-3a(v) — non-vacuous corpus + negative witness:
    [x] test_clean_no_stale_pointer_exits_zero
    [x] test_inline_pointer_to_done_target_emits_finding  (the negative witness)
    [x] test_annotation_pointer_to_done_target_emits_finding
    [x] test_prefix_pointer_to_done_target_emits_finding
    [x] test_pointer_to_non_done_target_exits_zero
    [x] test_landed_annotation_to_done_target_exits_zero  (flipped = not drift)
    [x] test_phase_and_soft_prose_to_done_keys_exits_zero (no false positives)
    [x] test_findings_are_byte_stable_ordered

AC-3a + CLI + harness-level error:
    [x] test_main_exit_two_when_carry_surface_unresolvable
    [x] test_main_exit_two_when_sprint_status_unresolvable
    [x] test_main_exit_two_on_malformed_sprint_status
    [x] test_main_exits_one_on_finding / test_main_exits_zero_on_clean
    [x] test_artifacts_dir_resolves_both_inputs

AC-4 — boundary witness (build-time gate, NO runtime marker).
"""

from __future__ import annotations

import pathlib

from loud_fail_harness.forward_pointer_drift import (
    iter_carry_pointers,
    iter_done_story_keys,
)
from loud_fail_harness.forward_pointer_drift_gate import (
    evaluate_forward_pointer_drift,
    main,
    run_forward_pointer_drift_gate,
)

_DONE = "18-3-concurrent-env-provisioning-discipline-fr7-extension"


def _sprint_status(**statuses: str) -> str:
    lines = ["development_status:"]
    lines.extend(f"  {key}: {value}" for key, value in statuses.items())
    return "\n".join(lines) + "\n"


def _evaluate(tmp_path: pathlib.Path, carry_text: str, sprint_text: str) -> object:
    carry_path = tmp_path / "deferred-work.md"
    return evaluate_forward_pointer_drift(
        carry_pointers=iter_carry_pointers(carry_text),
        done_story_keys=iter_done_story_keys(sprint_text),
        carry_surface_path=carry_path,
    )


# --------------------------------------------------------------------------- #
# Rule R1 — fixture corpus                                                     #
# --------------------------------------------------------------------------- #


def test_clean_no_stale_pointer_exits_zero(tmp_path: pathlib.Path) -> None:
    carry = "- deferred to 99-9-not-a-story per the retro\n"
    result = _evaluate(tmp_path, carry, _sprint_status(**{_DONE: "done"}))
    assert result.findings == ()


def test_inline_pointer_to_done_target_emits_finding(tmp_path: pathlib.Path) -> None:
    # THE negative witness: a carry entry whose target is `done`.
    carry = f"- some open item, deferred to {_DONE} per the Epic 18 retro\n"
    result = _evaluate(tmp_path, carry, _sprint_status(**{_DONE: "done"}))
    assert [f.rule for f in result.findings] == ["stale-forward-pointer"]
    assert _DONE in result.findings[0].diagnostic


def test_annotation_pointer_to_done_target_emits_finding(
    tmp_path: pathlib.Path,
) -> None:
    carry = f"- x <!-- forward-pointer: target={_DONE}; status=pending -->\n"
    result = _evaluate(tmp_path, carry, _sprint_status(**{_DONE: "done"}))
    assert [f.rule for f in result.findings] == ["stale-forward-pointer"]


def test_prefix_pointer_to_done_target_emits_finding(tmp_path: pathlib.Path) -> None:
    carry = "- carries to 18-3 per the Epic 18 retro\n"
    result = _evaluate(tmp_path, carry, _sprint_status(**{_DONE: "done"}))
    assert [f.rule for f in result.findings] == ["stale-forward-pointer"]


def test_pointer_to_non_done_target_exits_zero(tmp_path: pathlib.Path) -> None:
    # Target exists but is still in-flight (review) — legitimately open carry.
    carry = f"- carries to {_DONE} per the retro\n"
    result = _evaluate(tmp_path, carry, _sprint_status(**{_DONE: "review"}))
    assert result.findings == ()


def test_landed_annotation_to_done_target_exits_zero(tmp_path: pathlib.Path) -> None:
    # The pointer WAS flipped (status=landed) — not drift even though done.
    carry = f"- x <!-- forward-pointer: target={_DONE}; status=landed -->\n"
    result = _evaluate(tmp_path, carry, _sprint_status(**{_DONE: "done"}))
    assert result.findings == ()


def test_phase_and_soft_prose_to_done_keys_exits_zero(
    tmp_path: pathlib.Path,
) -> None:
    # Phase-level + soft prose must not fire even when a same-numbered story
    # is done — they carry no machine-checkable story-key binding.
    carry = (
        "- H10 carries to Phase 3 unchanged; trigger remains armed\n"
        "- Story 18.3 is the natural resolution point for this\n"
        "- Epic 18 Story 18.2 will exercise them later\n"
    )
    result = _evaluate(tmp_path, carry, _sprint_status(**{_DONE: "done"}))
    assert result.findings == ()


def test_findings_are_byte_stable_ordered(tmp_path: pathlib.Path) -> None:
    other = "14-3-story-file-locking-protocol"
    carry = (
        f"- carries to {other} (line 1)\n"
        f"- deferred to {_DONE} (line 2)\n"
    )
    sprint = _sprint_status(**{_DONE: "done", other: "done"})
    result = _evaluate(tmp_path, carry, sprint)
    keys = [(str(f.source_path), f.line_number, f.rule) for f in result.findings]
    assert keys == sorted(keys)
    assert result.findings[0].line_number == 1


def test_carry_pointers_scanned_counts_all_parsed(tmp_path: pathlib.Path) -> None:
    carry = (
        f"- deferred to {_DONE}\n"
        "- carries to 99-9-absent\n"
    )
    result = _evaluate(tmp_path, carry, _sprint_status(**{_DONE: "done"}))
    assert result.carry_pointers_scanned == 2
    assert len(result.findings) == 1


# --------------------------------------------------------------------------- #
# CLI + harness-level error paths                                             #
# --------------------------------------------------------------------------- #


def _write_pair(
    tmp_path: pathlib.Path, carry_text: str, sprint_text: str
) -> tuple[pathlib.Path, pathlib.Path]:
    carry = tmp_path / "deferred-work.md"
    sprint = tmp_path / "sprint-status.yaml"
    carry.write_text(carry_text, encoding="utf-8")
    sprint.write_text(sprint_text, encoding="utf-8")
    return carry, sprint


def test_main_exit_two_when_carry_surface_unresolvable(
    tmp_path: pathlib.Path,
) -> None:
    sprint = tmp_path / "sprint-status.yaml"
    sprint.write_text(_sprint_status(**{_DONE: "done"}), encoding="utf-8")
    code = main(
        [
            "--carry-surface",
            str(tmp_path / "nope.md"),
            "--sprint-status",
            str(sprint),
        ]
    )
    assert code == 2


def test_main_exit_two_when_sprint_status_unresolvable(
    tmp_path: pathlib.Path,
) -> None:
    carry = tmp_path / "deferred-work.md"
    carry.write_text("- nothing here\n", encoding="utf-8")
    code = main(
        [
            "--carry-surface",
            str(carry),
            "--sprint-status",
            str(tmp_path / "nope.yaml"),
        ]
    )
    assert code == 2


def test_main_exit_two_on_malformed_sprint_status(tmp_path: pathlib.Path) -> None:
    carry, sprint = _write_pair(
        tmp_path,
        "- nothing\n",
        "development_status:\n  - [unbalanced\n",
    )
    code = main(["--carry-surface", str(carry), "--sprint-status", str(sprint)])
    assert code == 2


def test_main_exits_one_on_finding(tmp_path: pathlib.Path) -> None:
    carry, sprint = _write_pair(
        tmp_path,
        f"- deferred to {_DONE} per the retro\n",
        _sprint_status(**{_DONE: "done"}),
    )
    code = main(["--carry-surface", str(carry), "--sprint-status", str(sprint)])
    assert code == 1


def test_main_exits_zero_on_clean(tmp_path: pathlib.Path) -> None:
    carry, sprint = _write_pair(
        tmp_path,
        "- deferred to 99-9-absent per the retro\n",
        _sprint_status(**{_DONE: "done"}),
    )
    code = main(["--carry-surface", str(carry), "--sprint-status", str(sprint)])
    assert code == 0


def test_artifacts_dir_resolves_both_inputs(tmp_path: pathlib.Path) -> None:
    artifacts = tmp_path / "_bmad-output" / "implementation-artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "deferred-work.md").write_text(
        f"- deferred to {_DONE}\n", encoding="utf-8"
    )
    (artifacts / "sprint-status.yaml").write_text(
        _sprint_status(**{_DONE: "done"}), encoding="utf-8"
    )
    code = main(["--artifacts-dir", str(artifacts)])
    assert code == 1


def test_run_gate_orchestrates_read_parse_evaluate(tmp_path: pathlib.Path) -> None:
    carry, sprint = _write_pair(
        tmp_path,
        f"- deferred to {_DONE}\n",
        _sprint_status(**{_DONE: "done"}),
    )
    result = run_forward_pointer_drift_gate(
        carry_surface_path=carry, sprint_status_path=sprint
    )
    assert result.done_stories_scanned == (_DONE,)
    assert len(result.findings) == 1


# --------------------------------------------------------------------------- #
# Boundary witness (AC-4) — build-time gate, NO runtime marker                #
# --------------------------------------------------------------------------- #


def test_new_modules_emit_no_runtime_marker() -> None:
    # Build-time gate: the two new modules must not touch the active_markers
    # surface, name a marker class, or load the marker taxonomy.
    src = pathlib.Path(__file__).resolve().parents[1] / "src" / "loud_fail_harness"
    for stem in ("forward_pointer_drift", "forward_pointer_drift_gate"):
        text = (src / f"{stem}.py").read_text(encoding="utf-8")
        assert "active_markers" not in text
        assert "marker_class=" not in text
        assert "marker-taxonomy" not in text
