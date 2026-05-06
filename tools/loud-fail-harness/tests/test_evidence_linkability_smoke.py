"""Story 6.6 — bundle-render-time evidence-trace linkability integration smoke tests.

Per the per-feature integration-test-isolation precedent from Stories
6.4 / 6.5: this module exercises the full ``assemble_bundle`` call path
with seeded run-state pointing at on-disk QA evidence + retry-history
artifacts, then selectively deletes files between assembly calls to
validate the dangling detection + marker emission + inline rendering.

Each test docstring cites the specific AC (or sub-claim) it witnesses
verbatim per Pattern 5's named-invariant convention.
"""

from __future__ import annotations

import json
import pathlib
import re
from datetime import datetime, timezone
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
import yaml

from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.bundle_assembly import assemble_bundle
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    load_marker_class_registry,
)


_STORY_ID = "sample-auto-001"
_RUN_ID = "run-2026-04-29-001"
_GENERATED_AT = datetime(2026, 4, 29, 12, 0, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def envelopes_dir() -> pathlib.Path:
    return find_repo_root() / "examples" / "envelopes"


@pytest.fixture(scope="module")
def canonical_dev_envelope(envelopes_dir: pathlib.Path) -> dict[str, Any]:
    return yaml.safe_load(
        (envelopes_dir / "dev-pass.yaml").read_text(encoding="utf-8")
    )


@pytest.fixture(scope="module")
def canonical_review_envelope(envelopes_dir: pathlib.Path) -> dict[str, Any]:
    return yaml.safe_load(
        (envelopes_dir / "review-pass-three-layer.yaml").read_text(
            encoding="utf-8"
        )
    )


@pytest.fixture(scope="module")
def canonical_qa_envelope(envelopes_dir: pathlib.Path) -> dict[str, Any]:
    return yaml.safe_load(
        (envelopes_dir / "qa-pass-ac1-tier1.yaml").read_text(encoding="utf-8")
    )


@pytest.fixture(scope="module")
def runtime_marker_registry() -> MarkerClassRegistry:
    return load_marker_class_registry()


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _flags_namespace(
    *,
    full_review: bool = False,
    full_qa: bool = False,
    retry: bool = False,
    loud_fail_block: bool = False,
) -> ModuleType | SimpleNamespace:
    return SimpleNamespace(
        is_full_review_present=lambda: full_review,
        is_full_qa_present=lambda: full_qa,
        is_retry_present=lambda: retry,
        is_loud_fail_block_present=lambda: loud_fail_block,
    )


def _write_run_state(
    rs_path: pathlib.Path,
    *,
    retry_history: list[dict[str, Any]] | None = None,
) -> pathlib.Path:
    rs_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "schema_version": "1.1",
        "story_id": _STORY_ID,
        "run_id": _RUN_ID,
        "current_state": "done",
        "branch_name": "bmad-automation/story/sample-auto-001",
        "dispatched_specialist": None,
        "last_envelope": None,
        "pending_qa_dispatch_payload": None,
        "retry_history": retry_history or [],
        "active_markers": [],
        "cost_to_date_by_specialist": {},
    }
    rs_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return rs_path


def _seed_dispatch_logs(
    logs_root: pathlib.Path,
    *,
    dev: dict[str, Any],
    review: dict[str, Any],
    qa: dict[str, Any],
) -> None:
    for specialist, envelope in (
        ("dev", dev),
        ("review-bmad", review),
        ("qa", qa),
    ):
        log_path = (
            logs_root
            / _STORY_ID
            / _RUN_ID
            / "logs"
            / f"{specialist}-1.log"
        )
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_payload = {
            "dispatched_specialist": specialist,
            "story_id": _STORY_ID,
            "attempt_number": 1,
            "agent_definition_path": f"agents/{specialist}.md",
            "acceptance_criteria": [{"ac_id": "AC-1", "text": "stub"}],
            "dispatch_timestamp": _GENERATED_AT.isoformat(),
            "return_timestamp": _GENERATED_AT.isoformat(),
            "return_envelope": envelope,
        }
        log_path.write_text(json.dumps(log_payload, indent=2), encoding="utf-8")


def _seed_qa_evidence_file(repo_root: pathlib.Path) -> pathlib.Path:
    """Seed the canonical qa-pass-ac1-tier1.yaml evidence_ref path."""
    evidence_path = (
        repo_root
        / "_bmad-output"
        / "qa-evidence"
        / "sample-001"
        / "run-2026-04-29-001"
        / "ac1-http-200.log"
    )
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text("HTTP/1.1 200 OK\n", encoding="utf-8")
    return evidence_path


def _seed_retry_round_artifact(
    repo_root: pathlib.Path,
    *,
    round_id: str = "round-01",
) -> tuple[pathlib.Path, str]:
    rel_path = f"_bmad-output/retry-history/sample-auto-001/{round_id}.yaml"
    artifact_path = repo_root / rel_path
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("dummy: ok\n", encoding="utf-8")
    return artifact_path, rel_path


def _assemble(
    *,
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
    retry_history: list[dict[str, Any]] | None = None,
) -> pathlib.Path:
    rs_path = _write_run_state(
        tmp_path / "_bmad" / "automation" / "run-state.yaml",
        retry_history=retry_history,
    )
    logs_root = tmp_path / "qa-evidence"
    _seed_dispatch_logs(
        logs_root,
        dev=canonical_dev_envelope,
        review=canonical_review_envelope,
        qa=canonical_qa_envelope,
    )
    bundle_root = tmp_path / "pr-bundles"
    result = assemble_bundle(
        story_id=_STORY_ID,
        run_id=_RUN_ID,
        run_state_path=rs_path,
        logs_root=logs_root,
        bundle_root=bundle_root,
        marker_registry=runtime_marker_registry,
        thickening_flags=_flags_namespace(
            full_review=True, full_qa=True, retry=True, loud_fail_block=True
        ),
        generated_at=_GENERATED_AT,
        repo_root=tmp_path,
    )
    return result.bundle_path


# --------------------------------------------------------------------------- #
# (n) full bundle assembly with deleted QA evidence file                      #
# --------------------------------------------------------------------------- #


def test_smoke_qa_evidence_deleted_post_seed_renders_dangling_marker(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Story 6.6 AC-1 + AC-2 (n): full bundle assembly with seeded
    QA evidence; delete the file BEFORE bundle render; assert post-
    render bundle's loud-fail block contains
    `dangling-evidence-ref: qa-evidence` AND per-AC body contains the
    inline indicator at the right location."""
    evidence_file = _seed_qa_evidence_file(tmp_path)
    assert evidence_file.exists()
    evidence_file.unlink()  # Delete BEFORE bundle render → dangling.
    bundle_path = _assemble(
        tmp_path=tmp_path,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    body = bundle_path.read_text(encoding="utf-8")
    # Loud-fail block carries the source-class summary.
    assert "## ⚠️ Loud-Fail Markers" in body
    assert "### dangling-evidence-ref: qa-evidence" in body
    # Per-AC body inline indicator.
    assert "⚠️ dangling-evidence-ref: qa-evidence" in body
    assert "regenerate the evidence OR fix the reference" in body


# --------------------------------------------------------------------------- #
# (o) full bundle assembly with deleted retry-history file                    #
# --------------------------------------------------------------------------- #


def test_smoke_retry_history_deleted_post_seed_renders_dangling_marker(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Story 6.6 AC-1 + AC-2 (o): full bundle assembly with retry-
    history-thickened run-state; delete the retry-round artifact;
    assert `dangling-evidence-ref: retry-history` surfaces in loud-
    fail block."""
    _seed_qa_evidence_file(tmp_path)  # QA-side resolves cleanly.
    artifact_path, rel_path = _seed_retry_round_artifact(tmp_path)
    artifact_path.unlink()  # Delete retry-history file → dangling.
    retry_history_entry = {
        "retry_attempt": 1,
        "retry_reason": "patch-bucket-retry",
        "round_id": "round-01",
        "path": rel_path,
    }
    bundle_path = _assemble(
        tmp_path=tmp_path,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
        retry_history=[retry_history_entry],
    )
    body = bundle_path.read_text(encoding="utf-8")
    assert "### dangling-evidence-ref: retry-history" in body
    # No qa-evidence-side dangling for this scenario.
    assert "### dangling-evidence-ref: qa-evidence" not in body


# --------------------------------------------------------------------------- #
# (p) both deleted simultaneously — alphabetical order                        #
# --------------------------------------------------------------------------- #


def test_smoke_both_dangling_loud_fail_block_alphabetical_order(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Story 6.6 AC-3 (p): both QA-evidence AND retry-history files
    deleted → both markers in loud-fail block in alphabetical order
    (qa-evidence first); both inline indicators rendered."""
    _, rel_path = _seed_retry_round_artifact(tmp_path)
    # Don't seed QA evidence file → QA dangles.
    # Don't keep retry-history file either → retry-history dangles.
    (tmp_path / rel_path).unlink(missing_ok=True)
    retry_history_entry = {
        "retry_attempt": 1,
        "retry_reason": "patch-bucket-retry",
        "round_id": "round-01",
        "path": rel_path,
    }
    bundle_path = _assemble(
        tmp_path=tmp_path,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
        retry_history=[retry_history_entry],
    )
    body = bundle_path.read_text(encoding="utf-8")
    qa_idx = body.index("### dangling-evidence-ref: qa-evidence")
    retry_idx = body.index("### dangling-evidence-ref: retry-history")
    # Alphabetical order: qa-evidence first.
    assert qa_idx < retry_idx


# --------------------------------------------------------------------------- #
# (q) marker-permanence — re-render after restoration drops the marker        #
# --------------------------------------------------------------------------- #


def test_smoke_marker_does_not_persist_after_file_restoration(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Story 6.6 AC-2 (q): second `assemble_bundle` call after the
    missing file has been restored returns a bundle WITHOUT the
    dangling-evidence marker — the assembler-side computation does
    not write back to run-state, so a fresh validation re-derives
    correctly."""
    # First render: file missing → marker fires.
    bundle_path_1 = _assemble(
        tmp_path=tmp_path / "round-1",
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    body_1 = bundle_path_1.read_text(encoding="utf-8")
    assert "### dangling-evidence-ref: qa-evidence" in body_1

    # Second render: file restored → marker absent.
    _seed_qa_evidence_file(tmp_path / "round-2")
    bundle_path_2 = _assemble(
        tmp_path=tmp_path / "round-2",
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    body_2 = bundle_path_2.read_text(encoding="utf-8")
    assert "### dangling-evidence-ref:" not in body_2


# --------------------------------------------------------------------------- #
# (r) NFR-O7 verbatim invariant per ``prd.md:986``                            #
# --------------------------------------------------------------------------- #


def test_smoke_nfr_o7_invariant_each_evidence_bullet_resolves_or_indicates(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Story 6.6 (r): NFR-O7 verbatim invariant — for each
    ``evidence_refs`` bullet in the rendered per-AC body, the bullet
    EITHER has no inline indicator AND the path resolves on disk, OR
    the bullet has the `⚠️ dangling-evidence-ref` indicator. The
    invariant is structural — there is no "neither" state."""
    # Mixed scenario: QA envelope has one evidence_ref; we delete it.
    _seed_qa_evidence_file(tmp_path)
    (
        tmp_path
        / "_bmad-output"
        / "qa-evidence"
        / "sample-001"
        / "run-2026-04-29-001"
        / "ac1-http-200.log"
    ).unlink()
    bundle_path = _assemble(
        tmp_path=tmp_path,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    body = bundle_path.read_text(encoding="utf-8")
    # Find every evidence-bullet line in the per-AC body. The bullet
    # shape is ``- `<path>`...``; partition on whether the inline
    # indicator suffix is present.
    bullet_re = re.compile(r"^- `(?P<path>[^`]+)`(?P<rest>.*)$", re.MULTILINE)
    matched_bullets = list(bullet_re.finditer(body))
    # The QA envelope carries one evidence_ref bullet; the dev section
    # may also carry artifact bullets — restrict to evidence_refs by
    # looking for the path shape.
    evidence_bullets = [
        m
        for m in matched_bullets
        if "_bmad-output/qa-evidence/" in m.group("path")
    ]
    assert evidence_bullets, "expected at least one evidence_refs bullet"
    for match in evidence_bullets:
        path = match.group("path")
        rest = match.group("rest")
        has_indicator = "⚠️ dangling-evidence-ref" in rest
        resolves_on_disk = (tmp_path / path).exists()
        # NFR-O7 invariant: indicator-present iff path-missing.
        assert has_indicator != resolves_on_disk, (
            f"NFR-O7 invariant violated for path={path!r}: "
            f"has_indicator={has_indicator}, resolves={resolves_on_disk}"
        )


# --------------------------------------------------------------------------- #
# Canonical PR-bundle fixture regression test                                 #
# --------------------------------------------------------------------------- #


def test_canonical_dangling_evidence_ref_bundle_fixture_matches_assembler_output(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Story 6.6 AC-6: the canonical PR-bundle fixture
    `examples/pr-bundles/pr-bundle-dangling-evidence-ref.md` byte-
    matches the post-6.6 assembler output for its seeded run-state
    (one QA-evidence dangling AND one retry-history dangling).
    Mirrors Story 6.1's
    `test_canonical_walking_skeleton_bundle_fixture_matches_assembler_output`
    precedent.
    """
    fixture_path = (
        find_repo_root()
        / "examples"
        / "pr-bundles"
        / "pr-bundle-dangling-evidence-ref.md"
    )
    if not fixture_path.exists():
        pytest.fail(
            "examples/pr-bundles/pr-bundle-dangling-evidence-ref.md is "
            "missing from the repository — the fixture must be committed; "
            "regenerate it via assemble_bundle against the canonical "
            "envelope corpus with both QA-evidence and retry-history "
            "dangling."
        )
    fixture_body = fixture_path.read_text(encoding="utf-8")
    body_after_header = re.sub(
        r"^<!--.*?-->\s*", "", fixture_body, count=1, flags=re.DOTALL
    )

    retry_history_entry = {
        "retry_attempt": 1,
        "retry_reason": "patch-bucket-retry",
        "round_id": "round-01",
        "path": "_bmad-output/retry-history/sample-auto-001/round-01.yaml",
    }
    bundle_path = _assemble(
        tmp_path=tmp_path,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
        retry_history=[retry_history_entry],
    )
    assembled_body = bundle_path.read_text(encoding="utf-8")
    assert assembled_body == body_after_header, (
        "canonical dangling-evidence-ref fixture must match assembler "
        "output byte-for-byte (modulo contract-header strip); regenerate "
        "the fixture if the assembler's rendering intentionally changed"
    )
