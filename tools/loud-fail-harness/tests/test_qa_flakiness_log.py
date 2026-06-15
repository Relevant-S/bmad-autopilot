"""Story 20.2 — flakiness-log schema + persistence (FR-P2-8).

Contract-pair coverage: the example fixtures validate clean through
``validate_flakiness_log`` (exit 0) AND deliberately-malformed documents are
rejected (exit 1) — the non-vacuous proof the validator has teeth. Plus the
substrate-library behavior: the pure ``append_run_record`` builder
(append-then-trim retention), the absent->None / corrupt->loud-fail load
policy, and the atomic persist round-trip that reuses
``run_state.atomic_write_text``.
"""

from __future__ import annotations

import datetime
import pathlib

import pytest
import yaml
from pydantic import ValidationError

from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.qa_flakiness_log import (
    DEFAULT_RETENTION_RUNS,
    FLAKINESS_LOG_ROOT,
    SCHEMA_VERSION,
    FlakinessAcHistory,
    FlakinessLog,
    FlakinessLogError,
    FlakinessRunRecord,
    allocate_timestamp,
    append_run_record,
    compute_flakiness_log_path,
    load_flakiness_log,
    main,
    persist_flakiness_log,
    validate_flakiness_log,
)


@pytest.fixture
def repo_root() -> pathlib.Path:
    return find_repo_root()


@pytest.fixture
def schema_file(repo_root: pathlib.Path) -> pathlib.Path:
    return repo_root / "schemas" / "qa-flakiness-log.yaml"


@pytest.fixture
def examples_dir(repo_root: pathlib.Path) -> pathlib.Path:
    return repo_root / "examples" / "qa-flakiness-logs"


def _record(**overrides: object) -> FlakinessRunRecord:
    kwargs: dict[str, object] = dict(
        run_id="20260615T120000Z",
        timestamp="2026-06-15T12:00:00Z",
        status="pass",
        retry_count_within_run=0,
        evidence_ref="_bmad-output/qa-evidence/20-2-test/20260615T120000Z/AC-1",
    )
    kwargs.update(overrides)
    return FlakinessRunRecord(**kwargs)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Contract-pair: fixtures validate clean (exit 0)                             #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "fixture_name",
    ["multi-ac-mixed-pass-fail.yaml", "single-run-single-ac.yaml"],
)
def test_example_fixtures_validate_clean(
    examples_dir: pathlib.Path, schema_file: pathlib.Path, fixture_name: str
) -> None:
    assert (
        validate_flakiness_log(examples_dir / fixture_name, schema_path=schema_file)
        == 0
    )


def test_example_fixtures_parse_into_model(examples_dir: pathlib.Path) -> None:
    for fixture in examples_dir.glob("*.yaml"):
        raw = yaml.safe_load(fixture.read_text(encoding="utf-8"))
        FlakinessLog.model_validate(raw)  # must not raise


# --------------------------------------------------------------------------- #
# Contract-pair: malformed documents are rejected (exit 1) — non-vacuous      #
# --------------------------------------------------------------------------- #


_MALFORMED_CASES = {
    "bad_status_enum": {
        "schema_version": "1.0",
        "story_id": "x",
        "acs": [
            {
                "ac_id": "AC-1",
                "runs": [
                    {
                        "run_id": "r1",
                        "timestamp": "2026-06-15T12:00:00Z",
                        "status": "flaky",
                        "retry_count_within_run": 0,
                        "evidence_ref": "ref",
                    }
                ],
            }
        ],
    },
    "negative_retry_count": {
        "schema_version": "1.0",
        "story_id": "x",
        "acs": [
            {
                "ac_id": "AC-1",
                "runs": [
                    {
                        "run_id": "r1",
                        "timestamp": "2026-06-15T12:00:00Z",
                        "status": "pass",
                        "retry_count_within_run": -1,
                        "evidence_ref": "ref",
                    }
                ],
            }
        ],
    },
    "missing_required_key": {
        "schema_version": "1.0",
        "story_id": "x",
        "acs": [
            {
                "ac_id": "AC-1",
                "runs": [
                    {
                        "run_id": "r1",
                        "timestamp": "2026-06-15T12:00:00Z",
                        "status": "pass",
                        "evidence_ref": "ref",
                    }
                ],
            }
        ],
    },
    "additional_property": {
        "schema_version": "1.0",
        "story_id": "x",
        "acs": [],
        "unexpected": True,
    },
}


@pytest.mark.parametrize("case", sorted(_MALFORMED_CASES))
def test_malformed_documents_rejected(
    tmp_path: pathlib.Path, schema_file: pathlib.Path, case: str
) -> None:
    bad = tmp_path / f"{case}.yaml"
    bad.write_text(yaml.safe_dump(_MALFORMED_CASES[case]), encoding="utf-8")
    assert validate_flakiness_log(bad, schema_path=schema_file) == 1


def test_non_mapping_document_rejected(
    tmp_path: pathlib.Path, schema_file: pathlib.Path
) -> None:
    bad = tmp_path / "list.yaml"
    bad.write_text("- a\n- b\n", encoding="utf-8")
    assert validate_flakiness_log(bad, schema_path=schema_file) == 1


def test_missing_file_is_harness_error(
    tmp_path: pathlib.Path, schema_file: pathlib.Path
) -> None:
    assert (
        validate_flakiness_log(tmp_path / "nope.yaml", schema_path=schema_file) == 2
    )


def test_cli_main_validates_fixture(
    examples_dir: pathlib.Path, schema_file: pathlib.Path
) -> None:
    fixture = examples_dir / "single-run-single-ac.yaml"
    assert main([str(fixture), "--schema", str(schema_file)]) == 0


# --------------------------------------------------------------------------- #
# allocate_timestamp                                                          #
# --------------------------------------------------------------------------- #


def test_allocate_timestamp_formats_injected_clock() -> None:
    now = datetime.datetime(2026, 6, 15, 12, 34, 56, tzinfo=datetime.timezone.utc)
    assert allocate_timestamp(now) == "2026-06-15T12:34:56Z"


def test_allocate_timestamp_rejects_naive() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        allocate_timestamp(datetime.datetime(2026, 6, 15, 12, 34, 56))


def test_allocate_timestamp_matches_schema_pattern(
    tmp_path: pathlib.Path, schema_file: pathlib.Path
) -> None:
    stamp = allocate_timestamp(
        datetime.datetime(2026, 1, 2, 3, 4, 5, tzinfo=datetime.timezone.utc)
    )
    log = FlakinessLog(
        story_id="20-2-test",
        acs=(FlakinessAcHistory(ac_id="AC-1", runs=(_record(timestamp=stamp),)),),
    )
    persist_flakiness_log(log, repo_root=tmp_path)
    path = compute_flakiness_log_path("20-2-test", repo_root=tmp_path)
    assert validate_flakiness_log(path, schema_path=schema_file) == 0


# --------------------------------------------------------------------------- #
# Model input-hardening (direct; corpus covers the registry-derived matrix)   #
# --------------------------------------------------------------------------- #


def test_run_record_rejects_whitespace_run_id() -> None:
    with pytest.raises(ValidationError):
        _record(run_id="   ")


def test_run_record_rejects_newline_evidence_ref() -> None:
    with pytest.raises(ValidationError):
        _record(evidence_ref="a\nb")


def test_run_record_accepts_slash_in_evidence_ref() -> None:
    rec = _record(evidence_ref="_bmad-output/qa-evidence/s/r/AC-1")
    assert "/" in rec.evidence_ref


def test_log_rejects_traversal_story_id() -> None:
    with pytest.raises(ValidationError):
        FlakinessLog(story_id="../escape", acs=())


# --------------------------------------------------------------------------- #
# append_run_record — pure builder, append-then-trim                          #
# --------------------------------------------------------------------------- #


def test_append_to_empty_log_creates_ac() -> None:
    rec = _record()
    log = append_run_record(None, story_id="20-2-test", ac_id="AC-1", record=rec)
    assert log.story_id == "20-2-test"
    assert log.schema_version == SCHEMA_VERSION
    assert len(log.acs) == 1
    assert log.acs[0].ac_id == "AC-1"
    assert log.acs[0].runs == (rec,)


def test_append_to_existing_ac_appends_newest_last() -> None:
    r1 = _record(run_id="r1")
    r2 = _record(run_id="r2")
    log = append_run_record(None, story_id="s", ac_id="AC-1", record=r1)
    log = append_run_record(log, story_id="s", ac_id="AC-1", record=r2)
    assert [r.run_id for r in log.acs[0].runs] == ["r1", "r2"]


def test_append_new_ac_leaves_others_untouched() -> None:
    log = append_run_record(None, story_id="s", ac_id="AC-1", record=_record(run_id="r1"))
    log = append_run_record(log, story_id="s", ac_id="AC-2", record=_record(run_id="r2"))
    by_id = {ac.ac_id: ac for ac in log.acs}
    assert set(by_id) == {"AC-1", "AC-2"}
    assert by_id["AC-1"].runs[0].run_id == "r1"
    assert by_id["AC-2"].runs[0].run_id == "r2"


def test_retention_trims_oldest_per_ac() -> None:
    log: FlakinessLog | None = None
    for i in range(5):
        log = append_run_record(
            log, story_id="s", ac_id="AC-1", record=_record(run_id=f"r{i}"), retention=3
        )
    assert log is not None
    assert [r.run_id for r in log.acs[0].runs] == ["r2", "r3", "r4"]


def test_default_retention_is_thirty() -> None:
    log: FlakinessLog | None = None
    for i in range(DEFAULT_RETENTION_RUNS + 5):
        log = append_run_record(
            log, story_id="s", ac_id="AC-1", record=_record(run_id=f"r{i}")
        )
    assert log is not None
    assert len(log.acs[0].runs) == DEFAULT_RETENTION_RUNS
    assert log.acs[0].runs[0].run_id == "r5"


def test_append_is_pure_does_not_mutate_input() -> None:
    original = append_run_record(None, story_id="s", ac_id="AC-1", record=_record(run_id="r1"))
    appended = append_run_record(original, story_id="s", ac_id="AC-1", record=_record(run_id="r2"))
    assert len(original.acs[0].runs) == 1
    assert len(appended.acs[0].runs) == 2


def test_append_rejects_retention_below_one() -> None:
    with pytest.raises(ValueError, match="retention"):
        append_run_record(None, story_id="s", ac_id="AC-1", record=_record(), retention=0)


def test_append_rejects_story_id_mismatch() -> None:
    log = append_run_record(None, story_id="s", ac_id="AC-1", record=_record())
    with pytest.raises(ValueError, match="story_id mismatch"):
        append_run_record(log, story_id="other", ac_id="AC-1", record=_record())


# --------------------------------------------------------------------------- #
# compute_flakiness_log_path                                                  #
# --------------------------------------------------------------------------- #


def test_compute_path_shape(tmp_path: pathlib.Path) -> None:
    path = compute_flakiness_log_path("20-2-test", repo_root=tmp_path)
    assert path == tmp_path / FLAKINESS_LOG_ROOT / "20-2-test.yaml"


def test_compute_path_rejects_traversal(tmp_path: pathlib.Path) -> None:
    with pytest.raises(ValueError):
        compute_flakiness_log_path("../escape", repo_root=tmp_path)


# --------------------------------------------------------------------------- #
# persist / load round-trip (atomic write reuse) + corrupt policy             #
# --------------------------------------------------------------------------- #


def test_persist_then_load_round_trips(tmp_path: pathlib.Path) -> None:
    log = append_run_record(None, story_id="20-2-test", ac_id="AC-1", record=_record())
    persist_flakiness_log(log, repo_root=tmp_path)
    loaded = load_flakiness_log("20-2-test", repo_root=tmp_path)
    assert loaded == log


def test_persisted_file_validates_against_schema(
    tmp_path: pathlib.Path, schema_file: pathlib.Path
) -> None:
    log = append_run_record(None, story_id="20-2-test", ac_id="AC-1", record=_record())
    log = append_run_record(log, story_id="20-2-test", ac_id="AC-1", record=_record(run_id="r2", status="fail", retry_count_within_run=3))
    persist_flakiness_log(log, repo_root=tmp_path)
    path = compute_flakiness_log_path("20-2-test", repo_root=tmp_path)
    assert validate_flakiness_log(path, schema_path=schema_file) == 0


def test_load_absent_returns_none(tmp_path: pathlib.Path) -> None:
    assert load_flakiness_log("never-written", repo_root=tmp_path) is None


def test_load_corrupt_yaml_loud_fails(tmp_path: pathlib.Path) -> None:
    path = compute_flakiness_log_path("20-2-test", repo_root=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("schema_version: '1.0'\n  : broken: [", encoding="utf-8")
    with pytest.raises(FlakinessLogError):
        load_flakiness_log("20-2-test", repo_root=tmp_path)


def test_load_schema_invalid_loud_fails(tmp_path: pathlib.Path) -> None:
    path = compute_flakiness_log_path("20-2-test", repo_root=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump({"schema_version": "1.0", "story_id": "x", "acs": [{"ac_id": "AC-1", "runs": [{"run_id": "r", "timestamp": "2026-06-15T12:00:00Z", "status": "nope", "retry_count_within_run": 0, "evidence_ref": "ref"}]}]}),
        encoding="utf-8",
    )
    with pytest.raises(FlakinessLogError):
        load_flakiness_log("20-2-test", repo_root=tmp_path)


def test_persist_reuses_run_state_atomic_write_text() -> None:
    import loud_fail_harness.qa_flakiness_log as mod
    from loud_fail_harness.run_state import atomic_write_text

    assert mod.atomic_write_text is atomic_write_text
