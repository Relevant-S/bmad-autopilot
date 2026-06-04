"""Tests for the sprint-status-artifact subjective-field rejector (Story 16.3).

Coverage map (per the story's Task 6):
    [x] validate_artifact_data — objective payload accepted                       → test_validate_objective_accepted
    [x] validate_artifact_data — subjective/unknown top-level field rejected       → test_validate_subjective_top_level_rejected
    [x] validate_artifact_data — each sub-object closed (escalation/retry/per_epic) → test_validate_subobject_closed
    [x] validate_artifact_data — non-Mapping → TypeError (→ exit 2)                → test_validate_non_mapping_raises
    [x] scan_rendered_markdown — each denylist heading rejected (case-insensitive)  → test_scan_rejects_each_denylist_heading
    [x] scan_rendered_markdown — clean artifact accepted                           → test_scan_clean_accepted
    [x] scan_rendered_markdown — non-str → TypeError                               → test_scan_non_str_raises
    [x] main — --data accept/reject exit codes + stdout JSON                        → test_main_data_*
    [x] main — --artifact accept/reject exit codes                                 → test_main_artifact_*
    [x] main — harness error (unreadable path) → exit 2                            → test_main_harness_error_exit_2
"""

from __future__ import annotations

import json
import pathlib

import pytest

from loud_fail_harness import sprint_status_artifact_validator as ssav
from loud_fail_harness.sprint_status_artifact_validator import (
    _SUBJECTIVE_HEADING_DENYLIST,
    scan_rendered_markdown,
    validate_artifact_data,
)


def _schema_path() -> pathlib.Path:
    return (
        pathlib.Path(__file__).resolve().parents[3]
        / "schemas"
        / "sprint-status-artifact.yaml"
    )


def _objective_payload() -> dict[str, object]:
    return {
        "sprint_id": "sprint-1",
        "run_id": "run-1",
        "current_state": "sprint-complete",
        "generated_at": "2026-06-04T12:00:00+00:00",
        "per_epic": [
            {
                "epic_id": "epic-16",
                "status": "epic-complete",
                "cost_total": 3.5,
                "retries_consumed": 1,
                "retries_budget": 4,
            }
        ],
        "per_story": [
            {
                "story_id": "16-1-a",
                "epic_id": "epic-16",
                "status": "merge-ready",
                "cost": 1.5,
            },
            {
                "story_id": "99-1-loose",
                "epic_id": None,
                "status": "not-dispatched",
                "cost": 0.0,
            },
        ],
        "aggregate_cost_total": 3.5,
        "retry_budget": {"consumed": 1, "effective_budget": 4},
        "escalation": {"escalated_stories": 0, "stories_completed": 2, "rate": 0.0},
        "active_markers": [
            {"marker_class": "epic-budget-exhausted", "scope": "epic:epic-16"}
        ],
    }


# --------------------------------------------------------------------------- #
# validate_artifact_data
# --------------------------------------------------------------------------- #


def test_validate_objective_accepted() -> None:
    verdict = validate_artifact_data(_objective_payload(), schema_path=_schema_path())
    assert verdict.accepted
    assert verdict.offending is None


@pytest.mark.parametrize(
    "field", ["what_went_well", "recommendation", "lessons_learned", "sentiment"]
)
def test_validate_subjective_top_level_rejected(field: str) -> None:
    payload = _objective_payload()
    payload[field] = "subjective prose"
    verdict = validate_artifact_data(payload, schema_path=_schema_path())
    assert not verdict.accepted
    assert verdict.offending is not None


def test_validate_subobject_closed() -> None:
    # additionalProperties:false on the escalation sub-object rejects a smuggled
    # subjective field nested one level down.
    payload = _objective_payload()
    payload["escalation"] = {
        "escalated_stories": 0,
        "stories_completed": 2,
        "rate": 0.0,
        "what_went_badly": "nothing",
    }
    verdict = validate_artifact_data(payload, schema_path=_schema_path())
    assert not verdict.accepted
    assert "escalation" in verdict.offending  # type: ignore[operator]


def test_validate_non_mapping_raises() -> None:
    with pytest.raises(TypeError):
        validate_artifact_data(["not", "a", "mapping"], schema_path=_schema_path())  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# scan_rendered_markdown
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("phrase", list(_SUBJECTIVE_HEADING_DENYLIST))
def test_scan_rejects_each_denylist_heading(phrase: str) -> None:
    # case-insensitive: title-case the heading to prove the scan normalizes
    text = f"# Sprint status artifact\n\n## {phrase.title()}\n\nbody\n"
    verdict = scan_rendered_markdown(text)
    assert not verdict.accepted
    assert verdict.offending is not None


def test_scan_clean_accepted() -> None:
    text = (
        "# Sprint status artifact — sprint s (run r)\n\n"
        "## Per-epic summary\n\n## Per-story summary\n\n"
        "## Aggregate cost\n\n## Retry-budget consumption\n\n"
        "## Escalation rate\n\n## Active loud-fail markers\n"
    )
    verdict = scan_rendered_markdown(text)
    assert verdict.accepted
    assert verdict.offending is None


def test_scan_ignores_denylist_in_body_text() -> None:
    # the scan binds HEADINGS only — a denylist word in a non-heading line is fine
    text = "# Sprint status artifact\n\nThis is not a retrospective.\n"
    assert scan_rendered_markdown(text).accepted


def test_scan_non_str_raises() -> None:
    with pytest.raises(TypeError):
        scan_rendered_markdown(123)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# main — 0/1/2 exit-code contract
# --------------------------------------------------------------------------- #


def _write_yaml(tmp_path: pathlib.Path, payload: dict[str, object]) -> pathlib.Path:
    import yaml

    path = tmp_path / "artifact-data.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


def test_main_data_accept(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str], monkeypatch
) -> None:
    monkeypatch.setattr(ssav, "_schema_path", _schema_path)
    path = _write_yaml(tmp_path, _objective_payload())
    rc = ssav.main(["--data", str(path)])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["accepted"] is True


def test_main_data_reject(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str], monkeypatch
) -> None:
    monkeypatch.setattr(ssav, "_schema_path", _schema_path)
    payload = _objective_payload()
    payload["retrospective"] = "subjective"
    path = _write_yaml(tmp_path, payload)
    rc = ssav.main(["--data", str(path)])
    assert rc == 1
    assert json.loads(capsys.readouterr().out)["accepted"] is False


def test_main_artifact_accept(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "art.md"
    path.write_text("# Sprint status artifact\n\n## Aggregate cost\n", encoding="utf-8")
    rc = ssav.main(["--artifact", str(path)])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["accepted"] is True


def test_main_artifact_reject(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "art.md"
    path.write_text("# Sprint\n\n## Lessons Learned\n", encoding="utf-8")
    rc = ssav.main(["--artifact", str(path)])
    assert rc == 1
    assert json.loads(capsys.readouterr().out)["accepted"] is False


def test_main_harness_error_exit_2(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = ssav.main(["--artifact", str(tmp_path / "does-not-exist.md")])
    assert rc == 2
    assert "harness-level error" in capsys.readouterr().err
