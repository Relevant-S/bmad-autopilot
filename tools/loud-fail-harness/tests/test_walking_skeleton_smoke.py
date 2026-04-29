"""End-to-end walking-skeleton smoke run (Story 2.13).

This module is the FIRST integration-test consumer that exercises all of the
Epic-2 substrate cohort simultaneously: ``run_state``, ``branch_lifecycle``,
``lifecycle_state_machine``, ``specialist_dispatch``, ``event_streaming``,
``bundle_assembly``, ``thickening_flags`` — driven against a fixture story
under ``tests/fixtures/sample-story-walking-skeleton.md`` with caller-injected
stub dispatch returning canned conformant Dev / Review-BMAD / QA envelopes.

The fixture is test infrastructure (per AC-1 of Story 2.13); it is NOT the
Epic-7 ``init``-scaffolded user-facing sample.

Contract-coverage matrix (AC-4 of Story 2.13):

    [x] full Epic-2 lifecycle (rfd → in-progress → review → qa → done)
        → test_walking_skeleton_smoke_run_end_to_end
    [x] events.jsonl every line validates against orchestrator-event.yaml
        → test_walking_skeleton_smoke_events_validate_against_schema
    [x] per-specialist log carries runtime_duration_ms (Story 2.12 additive)
        → test_walking_skeleton_smoke_per_specialist_logs_include_runtime_duration_ms
    [x] bundle has '## ⚠️ Walking Skeleton Mode' first content section
        → test_walking_skeleton_smoke_run_end_to_end
    [x] bundle has 'walking-skeleton-bundle' marker line
        → test_walking_skeleton_smoke_run_end_to_end
    [x] bundle does NOT carry loud-fail block / retry history sections
        → test_walking_skeleton_smoke_run_end_to_end
    [x] QA dispatch shape conforms to Story 2.1's TEA-handoff contract
        → test_walking_skeleton_smoke_qa_dispatch_exercises_tea_boundary_contract
    [x] thickening_flags.is_loud_fail_block_present flip suppresses the marker
        → test_walking_skeleton_smoke_bundle_thickening_flags_state
    [x] tmp_path scoping — no writes outside the test sandbox
        → test_walking_skeleton_smoke_run_end_to_end (asserts the bundle path
          + events log path + dispatch log paths all live under tmp_path)
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
import yaml

from loud_fail_harness import thickening_flags
from loud_fail_harness._shared import find_repo_root, load_schema
from loud_fail_harness.bundle_assembly import assemble_bundle
from loud_fail_harness.event_validator import validate_event
from loud_fail_harness.event_streaming import (
    default_event_log_path,
    make_event_log_appender,
)
from loud_fail_harness.lifecycle_state_machine import (
    EnvelopeOutcome,
    commit_transition,
    evaluate_envelope,
)
from loud_fail_harness.orchestrator_run_entry import (
    AcceptanceCriterion,
    DispatchCallbackResult,
    StoryDocResolution,
)
from loud_fail_harness.run_state import (
    CostToDateBySpecialist,
    RunState,
    StoryDocCallbackResult,
    advance_run_state,
)
from loud_fail_harness.specialist_dispatch import (
    SpecialistId,
    build_dispatch_payload,
    default_event_id_factory,
    default_prompt_body_renderer,
    load_marker_class_registry,
    make_specialist_dispatched_event,
    make_specialist_returned_event,
    persist_dispatch_log,
    validate_return_envelope_strict,
)
from loud_fail_harness.branch_lifecycle import (
    WorkingTreeProbeResult,
    create_story_branch,
)


# --------------------------------------------------------------------------- #
# Constants                                                                   #
# --------------------------------------------------------------------------- #


_FIXTURE_RELATIVE_PATH = pathlib.Path(
    "tools/loud-fail-harness/tests/fixtures/sample-story-walking-skeleton.md"
)

_STORY_ID = "sample-story-walking-skeleton"
_RUN_ID = "run-2026-04-29-smoke"
_BRANCH_NAME = f"bmad-automation/story/{_STORY_ID}"

# Specialist → real agent-definition filename map (the smoke test reads the
# real on-disk agent files via build_dispatch_payload to honor FR62 + ADR-004
# "agent definitions are read AS DATA, not imported").
_AGENT_FILENAME_BY_SPECIALIST: dict[SpecialistId, str] = {
    "dev": "dev-wrapper.md",
    "review-bmad": "review-bmad-wrapper.md",
    "qa": "qa.md",
}

# AC-1 single-AC contract for the fixture (mirrored verbatim into QA's canned
# envelope so the smoke test's bundle's per-AC section renders the AC-1 entry).
_FIXTURE_AC_ID = "AC-1"
_FIXTURE_AC_TEXT = (
    "The file `walking-skeleton-output.txt` exists at the run's working-"
    "directory root and contains the literal string "
    "`walking-skeleton-loop-completed`."
)


# --------------------------------------------------------------------------- #
# Fixture loading                                                             #
# --------------------------------------------------------------------------- #


def _load_walking_skeleton_fixture() -> tuple[dict[str, Any], str, pathlib.Path]:
    """Load the canonical fixture markdown via ``find_repo_root`` + relative path.

    Returns ``(frontmatter, body, fixture_path)``. Parallel to Story 1.7 / 1.8's
    canonical-fixture loading pattern: the fixture is read from its on-disk
    canonical location, NOT inlined into a tmp_path string.
    """
    fixture_path = find_repo_root() / _FIXTURE_RELATIVE_PATH
    raw = fixture_path.read_text(encoding="utf-8")
    # Frontmatter: bracketed by exactly two `---` lines at the top of the file.
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.DOTALL)
    assert match is not None, (
        f"fixture at {fixture_path} is missing YAML frontmatter delimited by "
        "`---` lines — programmer-error invariant"
    )
    frontmatter = yaml.safe_load(match.group(1))
    body = match.group(2)
    return frontmatter, body, fixture_path


@pytest.fixture(scope="module")
def fixture_data() -> tuple[dict[str, Any], str, pathlib.Path]:
    return _load_walking_skeleton_fixture()


@pytest.fixture(scope="module")
def envelope_schema() -> dict[str, Any]:
    return load_schema(find_repo_root() / "schemas" / "envelope.schema.yaml")


@pytest.fixture(scope="module")
def event_schema() -> dict[str, Any]:
    return load_schema(find_repo_root() / "schemas" / "orchestrator-event.yaml")


@pytest.fixture(scope="module")
def agents_dir() -> pathlib.Path:
    return find_repo_root() / "agents"


# --------------------------------------------------------------------------- #
# Stub envelope construction                                                  #
# --------------------------------------------------------------------------- #


def _make_canned_envelopes() -> dict[SpecialistId, dict[str, Any]]:
    """Produce the three canned conformant envelopes for the smoke run.

    Each envelope is structurally a happy-path return for its specialist:
    Dev's envelope carries a non-empty ``proposed_commit_message`` + an
    ``affected_files`` proxy via ``artifacts``; Review-BMAD's envelope is
    empty findings + empty failed_layers; QA's envelope carries exactly one
    ``ac_results`` entry for AC-1 with Tier-1-only evidence + ``not_applicable``
    semantic_verification — Story 2.10's AC-1-only invariant.
    """
    output_filename = "walking-skeleton-output.txt"

    dev_envelope: dict[str, Any] = {
        "status": "pass",
        "artifacts": [output_filename],
        "findings": [],
        "rationale": (
            "Wrote the literal string 'walking-skeleton-loop-completed' to "
            f"{output_filename} at the run's working-directory root; AC-1 is "
            "mechanically verifiable on file existence + string presence."
        ),
        "proposed_commit_message": (
            f"[bmad-automation story/{_STORY_ID}] add {output_filename}"
        ),
        "scope_expanded_to": [],
    }

    review_envelope: dict[str, Any] = {
        "status": "pass",
        "artifacts": [],
        "findings": [],
        "rationale": (
            "Acceptance Auditor reviewed the single AC against the Dev "
            "commit; no AC violations; no findings escalated to the patch "
            "bucket."
        ),
        "failed_layers": [],
    }

    qa_envelope: dict[str, Any] = {
        "status": "pass",
        "artifacts": [output_filename],
        "findings": [],
        "rationale": (
            "AC-1 verified mechanically: target file exists at the run's "
            "working-directory root and contains the expected literal "
            "string. Tier-1 evidence captured."
        ),
        "ac_results": [
            {
                "ac_id": _FIXTURE_AC_ID,
                "status": "pass",
                "assertions": [
                    f"file `{output_filename}` exists at the run's "
                    "working-directory root",
                    "file contents contain the literal string "
                    "`walking-skeleton-loop-completed`",
                ],
                "evidence_refs": [output_filename],
                "semantic_verification": "not_applicable",
            }
        ],
    }
    return {"dev": dev_envelope, "review-bmad": review_envelope, "qa": qa_envelope}


def _validate_canned_envelopes(
    envelopes: dict[SpecialistId, dict[str, Any]],
    schema: dict[str, Any],
) -> None:
    """Pre-validate every canned envelope at construction time per AC-4.

    Failing here is a programmer-error invariant — the smoke test's stubs
    must produce schema-conformant envelopes per the same Pattern 5 loud-fail
    discipline that production wrappers honor. Validation BEFORE the smoke
    run starts means a malformed stub is surfaced at stub-construction time,
    not at consumer parse-time.
    """
    for specialist, envelope in envelopes.items():
        validate_return_envelope_strict(envelope, schema)
        assert envelope["status"] == "pass", (
            f"smoke-test invariant: canned {specialist!r} envelope must have "
            "status=pass for the happy-path lifecycle to advance"
        )


# --------------------------------------------------------------------------- #
# Stub dispatch callback                                                      #
# --------------------------------------------------------------------------- #


def _make_stub_dispatch_callback(
    *,
    canned_envelopes: dict[SpecialistId, dict[str, Any]],
    agents_dir: pathlib.Path,
    qa_evidence_root: pathlib.Path,
    run_id: str,
) -> Callable[..., DispatchCallbackResult]:
    """Construct a dispatch callback that mimics the LLM-runtime Task-tool path.

    Per Story 2.6's caller-injected ``DispatchCallback`` seam, the callback
    accepts ``(specialist, story_id, run_state_path, story_doc_resolution,
    event_log_appender)`` and returns a :class:`DispatchCallbackResult`.

    The stub composes the Story 2.6 substrate primitives against the canned
    envelope:
        1. Build a :class:`SpecialistDispatchPayload` (reads the agent
           definition file as data per FR62).
        2. Emit a ``specialist-dispatched`` orchestrator event.
        3. Persist the dispatch log carrying the canned envelope (with the
           Story 2.12 additive ``runtime_duration_ms`` field).
        4. Emit a ``specialist-returned`` orchestrator event with the persisted
           log path as ``envelope_artifact_path``.

    The stub returns ``DispatchCallbackResult(dispatched=True, ...)`` —
    Pattern 5 sensor-not-advisor: the dispatch outcome is stamped on the
    result object; flow policy lives in the orchestrator (the test driver).
    """

    def stub_dispatch(
        *,
        specialist: SpecialistId,
        story_id: str,
        run_state_path: pathlib.Path,
        story_doc_resolution: StoryDocResolution,
        event_log_appender: Callable[[dict[str, Any]], None],
    ) -> DispatchCallbackResult:
        del run_state_path  # accepted for signature symmetry; unused here.
        envelope = canned_envelopes[specialist]
        agent_path = agents_dir / _AGENT_FILENAME_BY_SPECIALIST[specialist]

        # Use a fixed dispatch timestamp factory so the stub is deterministic.
        dispatch_ts = datetime.now(timezone.utc)
        payload = build_dispatch_payload(
            specialist=specialist,
            story_id=story_id,
            attempt_number=1,
            story_doc_resolution=story_doc_resolution,
            agent_definition_path=agent_path,
            prompt_body_renderer=default_prompt_body_renderer,
            dispatch_timestamp_factory=lambda: dispatch_ts,
        )
        dispatched_event = make_specialist_dispatched_event(
            payload, event_id_factory=default_event_id_factory
        )
        event_log_appender(dispatched_event)

        # Force a positive runtime_duration_ms so persist_dispatch_log's
        # NTP-skew guard passes and the AC-4 Subtask 2.7 assertion sees a
        # non-negative integer.
        return_ts = dispatch_ts + timedelta(milliseconds=1)
        log_path = persist_dispatch_log(
            payload, envelope, return_ts, qa_evidence_root, run_id=run_id
        )

        returned_event = make_specialist_returned_event(
            payload,
            envelope,
            event_id_factory=default_event_id_factory,
            return_timestamp=return_ts,
            envelope_artifact_path=log_path,
        )
        event_log_appender(returned_event)

        return DispatchCallbackResult(
            dispatched=True,
            reason=f"smoke-test stub dispatched specialist={specialist!r}",
        )

    return stub_dispatch


# --------------------------------------------------------------------------- #
# Run-state helpers                                                           #
# --------------------------------------------------------------------------- #


def _make_run_state(current_state: str) -> RunState:
    return RunState(
        schema_version="1.0",
        story_id=_STORY_ID,
        run_id=_RUN_ID,
        current_state=current_state,  # type: ignore[arg-type]
        branch_name=_BRANCH_NAME,
        dispatched_specialist=None,
        last_envelope=None,
        pending_qa_dispatch_payload=None,
        retry_history=(),
        active_markers=(),
        cost_to_date_by_specialist=CostToDateBySpecialist(),
    )


def _accepting_story_doc_callback() -> StoryDocCallbackResult:
    """Trivial story-doc callback for the smoke run.

    Returns ``accepted=True`` without touching any story-doc file. The smoke
    run's lifecycle transitions are gated on substrate composition, NOT on
    actual story-doc edits — those happen at LLM-runtime. The callback is
    the substrate-level seam Pattern 4 + NFR-R8 require for ordering; the
    smoke test honors the seam without exercising the (out-of-scope at Epic-2)
    story-doc-validator integration.
    """
    return StoryDocCallbackResult(
        accepted=True,
        reason="smoke-test no-op: no story-doc edit at this seam",
    )


# --------------------------------------------------------------------------- #
# Smoke-run driver                                                            #
# --------------------------------------------------------------------------- #


class _SmokeRunResult:
    """Carrier for the smoke-run's terminal artifacts (assertion-friendly)."""

    def __init__(
        self,
        *,
        branch_name: str,
        events_log_path: pathlib.Path,
        bundle_path: pathlib.Path,
        bundle_text: str,
        bundle_emitted_markers: tuple[str, ...],
        run_state_path: pathlib.Path,
        qa_evidence_root: pathlib.Path,
        canned_envelopes: dict[SpecialistId, dict[str, Any]],
        story_doc_resolution: StoryDocResolution,
    ) -> None:
        self.branch_name = branch_name
        self.events_log_path = events_log_path
        self.bundle_path = bundle_path
        self.bundle_text = bundle_text
        self.bundle_emitted_markers = bundle_emitted_markers
        self.run_state_path = run_state_path
        self.qa_evidence_root = qa_evidence_root
        self.canned_envelopes = canned_envelopes
        self.story_doc_resolution = story_doc_resolution


def _drive_smoke_run(
    *,
    tmp_path: pathlib.Path,
    fixture_path: pathlib.Path,
    envelope_schema: dict[str, Any],
    agents_dir: pathlib.Path,
) -> _SmokeRunResult:
    """Execute the full Epic-2 lifecycle against the walking-skeleton fixture.

    All filesystem writes are scoped under ``tmp_path``; nothing leaks outside
    the test sandbox. The run composes the Epic-2 substrate libraries directly
    (the "or the equivalent orchestrator-skill substrate composition seam"
    branch of Story 2.13 AC-4) — the smoke test does NOT call
    ``run_story_loop_entry`` because that introduces a cross-module class
    identity coupling with ``test_branch_lifecycle.py``'s ``importlib.reload``
    test (which reloads ``branch_lifecycle`` and invalidates
    ``RunStoryLoopEntryResult``'s pre-reload ``BranchLifecycleResult`` field
    annotation). Direct substrate composition is the canonical pattern Story
    2.5's orchestrator-skill prose at ``skills/bmad-automation/steps/run.md``
    describes; the smoke test materializes it in Python.

    Lifecycle phases:
        1. ``create_story_branch`` — branch_lifecycle (Story 2.3).
        2. ``advance_run_state`` — init at ``ready-for-dev`` (Story 2.2).
        3. ``commit_transition`` — rfd → in-progress (Story 2.4).
        4. Stub dispatch — Dev (Story 2.6 + 2.8 wrapper).
        5. ``commit_transition`` — in-progress → review.
        6. Stub dispatch — Review-BMAD (Story 2.9 wrapper).
        7. ``commit_transition`` — review → qa.
        8. Stub dispatch — QA (Story 2.10 wrapper; the TEA-handoff seam from
           Story 2.1).
        9. ``commit_transition`` — qa → done.
        10. ``assemble_bundle`` — final merge-ready PR bundle markdown
            (Story 2.11) using ``thickening_flags`` (Story 2.11) and Story
            2.12's per-event JSONL appender for the events.jsonl emission
            stream.
    """
    qa_evidence_root = tmp_path / "qa-evidence"
    bundle_root = tmp_path / "pr-bundles"
    run_state_path = tmp_path / "run-state.yaml"
    events_log_path = default_event_log_path(qa_evidence_root, _STORY_ID, _RUN_ID)

    # Initialize a tmp_path-scoped git repo so create_story_branch's git
    # subprocess calls succeed without touching the host repo. Story 2.13
    # Dev Notes (line 241): "the smoke test supplies a stub or uses a real
    # tmp_path-scoped git repo (whichever is simpler — dev's-call)". The
    # real-git approach exercises Story 2.3's branch_lifecycle authentically.
    _init_tmp_git_repo(tmp_path)

    canned_envelopes = _make_canned_envelopes()
    _validate_canned_envelopes(canned_envelopes, envelope_schema)

    story_doc_resolution = StoryDocResolution(
        path=fixture_path,
        current_state="ready-for-dev",
        acceptance_criteria=(
            AcceptanceCriterion(ac_id=_FIXTURE_AC_ID, text=_FIXTURE_AC_TEXT),
        ),
    )

    def clean_probe() -> WorkingTreeProbeResult:
        return WorkingTreeProbeResult(
            clean=True, uncommitted_paths=(), reason=None
        )

    appender = make_event_log_appender(events_log_path, fsync=False)
    stub_dispatch = _make_stub_dispatch_callback(
        canned_envelopes=canned_envelopes,
        agents_dir=agents_dir,
        qa_evidence_root=qa_evidence_root,
        run_id=_RUN_ID,
    )

    # Phase 1: branch_lifecycle (Story 2.3).
    branch_result = create_story_branch(
        _STORY_ID,
        trunk_allowlist=("main", "master", "trunk"),
        working_tree_probe=clean_probe,
        repo_root=tmp_path,
    )

    # Phase 2: init run-state (Story 2.2). The story doc already exists per
    # the fixture; init uses an accepting story-doc callback to honor the
    # NFR-R8 ordering invariant without exercising story-doc writes.
    initial_state = _make_run_state("ready-for-dev")
    advance_run_state(
        run_state_path=run_state_path,
        next_state=initial_state,
        story_doc_callback=_accepting_story_doc_callback,
    )

    # Phase 3: rfd → in-progress (Story 2.4 commit_transition).
    in_progress_state = _make_run_state("in-progress")
    commit_transition(
        run_state_path,
        initial_state,
        in_progress_state,
        story_doc_callback=_accepting_story_doc_callback,
        event_log_appender=appender,
    )

    # Phase 4: dispatch Dev (Story 2.6 + 2.8 wrapper).
    stub_dispatch(
        specialist="dev",
        story_id=_STORY_ID,
        run_state_path=run_state_path,
        story_doc_resolution=story_doc_resolution,
        event_log_appender=appender,
    )

    # Phase 5: in-progress → review.
    review_state = _make_run_state("review")
    decision = evaluate_envelope(
        "in-progress", "dev", _envelope_outcome(canned_envelopes["dev"])
    )
    assert decision.type == "advance" and decision.next_state == "review"
    commit_transition(
        run_state_path,
        in_progress_state,
        review_state,
        story_doc_callback=_accepting_story_doc_callback,
        event_log_appender=appender,
    )

    # Phase 6: dispatch Review-BMAD (Story 2.9 wrapper).
    stub_dispatch(
        specialist="review-bmad",
        story_id=_STORY_ID,
        run_state_path=run_state_path,
        story_doc_resolution=story_doc_resolution,
        event_log_appender=appender,
    )

    # Phase 7: review → qa.
    qa_state = _make_run_state("qa")
    decision = evaluate_envelope(
        "review", "review-bmad", _envelope_outcome(canned_envelopes["review-bmad"])
    )
    assert decision.type == "advance" and decision.next_state == "qa"
    commit_transition(
        run_state_path,
        review_state,
        qa_state,
        story_doc_callback=_accepting_story_doc_callback,
        event_log_appender=appender,
    )

    # Phase 8: dispatch QA — the TEA-handoff boundary surface from Story 2.1
    # (Story 2.10 AC-1-only / Tier-1-only wrapper).
    stub_dispatch(
        specialist="qa",
        story_id=_STORY_ID,
        run_state_path=run_state_path,
        story_doc_resolution=story_doc_resolution,
        event_log_appender=appender,
    )

    # Phase 9: qa → done.
    done_state = _make_run_state("done")
    decision = evaluate_envelope(
        "qa", "qa", _envelope_outcome(canned_envelopes["qa"])
    )
    assert decision.type == "advance" and decision.next_state == "done"
    commit_transition(
        run_state_path,
        qa_state,
        done_state,
        story_doc_callback=_accepting_story_doc_callback,
        event_log_appender=appender,
    )

    # Phase 10: assemble bundle from the persisted dispatch logs + run-state.
    bundle_result = assemble_bundle(
        story_id=_STORY_ID,
        run_id=_RUN_ID,
        run_state_path=run_state_path,
        logs_root=qa_evidence_root,
        bundle_root=bundle_root,
        marker_registry=load_marker_class_registry(),
        envelope_schema=envelope_schema,
    )
    bundle_text = bundle_result.bundle_path.read_text(encoding="utf-8")

    return _SmokeRunResult(
        branch_name=branch_result.branch_name,
        events_log_path=events_log_path,
        bundle_path=bundle_result.bundle_path,
        bundle_text=bundle_text,
        bundle_emitted_markers=bundle_result.emitted_markers,
        run_state_path=run_state_path,
        qa_evidence_root=qa_evidence_root,
        canned_envelopes=canned_envelopes,
        story_doc_resolution=story_doc_resolution,
    )


def _envelope_outcome(envelope: dict[str, Any]) -> EnvelopeOutcome:
    """Cast an envelope's ``status`` to the lifecycle-state-machine outcome literal.

    The envelope schema's ``status`` enum is ``[pass, fail, blocked]`` while
    the state machine accepts the additional ``decision-needed`` value
    (review-stage outcome). For the happy-path smoke run the cast is always
    ``"pass"``.
    """
    status = envelope["status"]
    assert status in ("pass", "fail", "blocked"), (
        f"smoke-test invariant: envelope status {status!r} is outside the "
        "envelope.schema.yaml enum"
    )
    return status  # type: ignore[return-value]


def _init_tmp_git_repo(repo_root: pathlib.Path) -> None:
    """Initialize a minimal git repo under ``repo_root`` with a single commit.

    Story 2.3's ``create_story_branch`` invokes real ``git`` subprocess calls
    against ``repo_root``; without an initialized repo the calls fail at the
    OS layer. The smoke test creates a clean repo on the default branch
    ``main`` (the orchestrator's trunk-allowlist excludes
    ``bmad-automation/story/<id>`` from the protected set) with a single
    seed commit so ``git checkout -b`` has a valid HEAD to branch off.

    The repo is fully scoped under ``repo_root`` (which is ``tmp_path`` for
    the smoke test) — no host-repo state is touched.
    """
    common = dict(cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "init", "--initial-branch=main"], **common)  # type: ignore[arg-type]
    subprocess.run(["git", "config", "user.email", "smoke@test.invalid"], **common)  # type: ignore[arg-type]
    subprocess.run(["git", "config", "user.name", "Smoke Test"], **common)  # type: ignore[arg-type]
    subprocess.run(["git", "config", "commit.gpgsign", "false"], **common)  # type: ignore[arg-type]
    (repo_root / "README.md").write_text("smoke-test seed\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], **common)  # type: ignore[arg-type]
    subprocess.run(["git", "commit", "-m", "seed"], **common)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Smoke-run fixture (function-scoped — tmp_path is function-scoped)            #
# --------------------------------------------------------------------------- #


@pytest.fixture
def smoke_run(
    tmp_path: pathlib.Path,
    fixture_data: tuple[dict[str, Any], str, pathlib.Path],
    envelope_schema: dict[str, Any],
    agents_dir: pathlib.Path,
) -> _SmokeRunResult:
    _, _, fixture_path = fixture_data
    return _drive_smoke_run(
        tmp_path=tmp_path,
        fixture_path=fixture_path,
        envelope_schema=envelope_schema,
        agents_dir=agents_dir,
    )


# --------------------------------------------------------------------------- #
# Tests — AC-4                                                                #
# --------------------------------------------------------------------------- #


def test_walking_skeleton_smoke_run_end_to_end(
    smoke_run: _SmokeRunResult, tmp_path: pathlib.Path
) -> None:
    """Full Epic-2 lifecycle smoke run: rfd → in-progress → review → qa → done.

    Asserts the bundle's structural shape per AC-4: the
    ``## ⚠️ Walking Skeleton Mode`` H2 is the FIRST content section after
    the H1 + metadata block; the ``walking-skeleton-bundle`` marker line is
    present (Story 2.11 AC-2 + AC-5); the bundle does NOT contain the
    Epic-5 retry-history section or the Epic-6 loud-fail-block section.
    Asserts the bundle's per-AC + review + Dev sections render the canned
    envelopes' content. Asserts every emitted artifact lives under
    ``tmp_path`` per the test-isolation contract.
    """
    bundle = smoke_run.bundle_text

    # First H2 is Walking Skeleton Mode (per Story 2.11 AC-2).
    h2_headers = re.findall(r"^## .+$", bundle, re.MULTILINE)
    assert h2_headers, "bundle has no H2 sections"
    assert h2_headers[0] == "## ⚠️ Walking Skeleton Mode", (
        f"first H2 is {h2_headers[0]!r}, expected '## ⚠️ Walking Skeleton Mode'"
    )

    # Walking-skeleton-bundle marker is present (machine-readable per Story 2.11 AC-5).
    assert "walking-skeleton-bundle" in smoke_run.bundle_emitted_markers
    assert "<!-- bmad-automation:marker walking-skeleton-bundle -->" in bundle

    # No Epic-5 retry-history section, no Epic-6 loud-fail-block section.
    assert "## Loud-fail" not in bundle
    assert "## Retry history" not in bundle
    assert "## Loud-Fail" not in bundle  # case-insensitive belt-and-suspenders

    # Per-AC section renders Story 2.10's exactly-one-entry shape.
    assert "## Per-AC results" in bundle
    assert _FIXTURE_AC_ID in bundle
    assert "**Semantic verification:** `not_applicable`" in bundle

    # Review findings empty + failed_layers empty.
    assert "## Review findings" in bundle
    assert "_(no findings)_" in bundle
    assert "Failed layers: (none)" in bundle

    # Dev section: proposed_commit_message verbatim.
    assert "## Dev" in bundle
    assert smoke_run.canned_envelopes["dev"]["proposed_commit_message"] in bundle

    # Branch + final state metadata block.
    assert _BRANCH_NAME in bundle
    assert "Final state: done" in bundle

    # Every emitted artifact lives under tmp_path (no leaks outside the sandbox).
    assert smoke_run.bundle_path.is_relative_to(tmp_path)
    assert smoke_run.events_log_path.is_relative_to(tmp_path)
    assert smoke_run.run_state_path.is_relative_to(tmp_path)
    assert smoke_run.qa_evidence_root.is_relative_to(tmp_path)


def test_walking_skeleton_smoke_qa_dispatch_exercises_tea_boundary_contract(
    smoke_run: _SmokeRunResult,
) -> None:
    """The QA dispatch step exercises Story 2.1's TEA-handoff boundary contract.

    Asserts QA's ``ac_results`` carries exactly one entry for AC-1 with
    ``status=pass``, non-empty ``assertions``, non-empty ``evidence_refs``
    (Tier-1 mechanical), and ``semantic_verification: not_applicable`` —
    Story 2.10's AC-1-only / Tier-1-only invariant. Asserts the QA wrapper
    agent definition the smoke run consumes is ``agents/qa.md``.
    """
    qa_envelope = smoke_run.canned_envelopes["qa"]
    ac_results = qa_envelope["ac_results"]
    assert len(ac_results) == 1
    entry = ac_results[0]
    assert entry["ac_id"] == _FIXTURE_AC_ID
    assert entry["status"] == "pass"
    assert len(entry["assertions"]) >= 1
    assert len(entry["evidence_refs"]) >= 1
    assert entry["semantic_verification"] == "not_applicable"

    # The QA wrapper definition path: agents/qa.md (Story 2.10's landing).
    qa_log_path = (
        smoke_run.qa_evidence_root
        / _STORY_ID
        / _RUN_ID
        / "logs"
        / "qa-1.log"
    )
    assert qa_log_path.exists()
    qa_log = json.loads(qa_log_path.read_text(encoding="utf-8"))
    assert qa_log["agent_definition_path"].endswith("agents/qa.md")


def test_walking_skeleton_smoke_events_validate_against_schema(
    smoke_run: _SmokeRunResult, event_schema: dict[str, Any]
) -> None:
    """Every line of events.jsonl validates against orchestrator-event.yaml.

    The structural seam between Story 2.12 (event production) and Story 1.3
    (event schema authoring): per AC-4 the smoke run asserts schema
    conformance line-by-line so a malformed event would fail the smoke test
    loudly per Pattern 5.

    Asserts the canonical lifecycle-event sequence is present: state-transition
    for each forward seam (rfd→ip, ip→review, review→qa, qa→done) plus
    specialist-dispatched + specialist-returned for each of Dev / Review-BMAD /
    QA — six dispatch events total.
    """
    events_text = smoke_run.events_log_path.read_text(encoding="utf-8")
    events = [json.loads(line) for line in events_text.splitlines() if line.strip()]
    assert events, "events.jsonl is empty"

    for event in events:
        errors = validate_event(event, event_schema)
        assert not errors, (
            f"event {event.get('event_id', '?')!r} of class "
            f"{event.get('event_class', '?')!r} failed schema validation: "
            f"{[str(e.message) for e in errors]}"
        )

    classes = [e["event_class"] for e in events]
    state_transitions = [e for e in events if e["event_class"] == "state-transition"]
    transitions = [
        (e["from_state"], e["to_state"]) for e in state_transitions
    ]
    assert ("ready-for-dev", "in-progress") in transitions
    assert ("in-progress", "review") in transitions
    assert ("review", "qa") in transitions
    assert ("qa", "done") in transitions

    # Three dispatched + three returned events (one per specialist).
    assert classes.count("specialist-dispatched") == 3
    assert classes.count("specialist-returned") == 3
    dispatched_specialists = sorted(
        e["specialist"] for e in events if e["event_class"] == "specialist-dispatched"
    )
    assert dispatched_specialists == ["dev", "qa", "review-bmad"]


def test_walking_skeleton_smoke_per_specialist_logs_include_runtime_duration_ms(
    smoke_run: _SmokeRunResult,
) -> None:
    """Every per-specialist dispatch log carries Story 2.12's additive
    ``runtime_duration_ms`` field as a non-negative integer.
    """
    logs_dir = smoke_run.qa_evidence_root / _STORY_ID / _RUN_ID / "logs"
    for specialist in ("dev", "review-bmad", "qa"):
        log_path = logs_dir / f"{specialist}-1.log"
        assert log_path.exists(), f"missing dispatch log for {specialist!r}"
        payload = json.loads(log_path.read_text(encoding="utf-8"))
        assert "runtime_duration_ms" in payload, (
            f"{specialist!r} log missing runtime_duration_ms (Story 2.12 additive)"
        )
        duration = payload["runtime_duration_ms"]
        assert isinstance(duration, int)
        assert duration >= 0, (
            f"{specialist!r} runtime_duration_ms is negative ({duration}); "
            "NTP-skew / monotonicity invariant violation"
        )


def test_walking_skeleton_smoke_bundle_thickening_flags_state(
    tmp_path: pathlib.Path,
    fixture_data: tuple[dict[str, Any], str, pathlib.Path],
    envelope_schema: dict[str, Any],
    agents_dir: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Walking Skeleton Mode marker is dynamically conditioned on
    ``thickening_flags.is_loud_fail_block_present`` per Story 2.11 AC-5.

    Drives the smoke run twice in two separate ``tmp_path`` sandboxes:
    once with the canonical Epic-2 flag state (returns ``False``; marker
    emitted) and once with the flag patched to ``True`` (Epic-6 substrate
    state simulation; marker suppressed). Confirms the structural-condition
    contract: the marker emission inverts on the flag's return value, NOT
    on a hardcoded "if Epic == 2" check.

    Per Subtask 2.8: after the assertion the patch is reverted (pytest's
    ``monkeypatch`` fixture handles teardown automatically).
    """
    _, _, fixture_path = fixture_data

    # Run 1: canonical Epic-2 flag state — marker emitted.
    sandbox_a = tmp_path / "sandbox-flag-false"
    sandbox_a.mkdir()
    result_false = _drive_smoke_run(
        tmp_path=sandbox_a,
        fixture_path=fixture_path,
        envelope_schema=envelope_schema,
        agents_dir=agents_dir,
    )
    assert "walking-skeleton-bundle" in result_false.bundle_emitted_markers
    assert (
        "<!-- bmad-automation:marker walking-skeleton-bundle -->"
        in result_false.bundle_text
    )

    # Run 2: patched flag state — marker suppressed.
    monkeypatch.setattr(
        thickening_flags, "is_loud_fail_block_present", lambda: True
    )
    sandbox_b = tmp_path / "sandbox-flag-true"
    sandbox_b.mkdir()
    result_true = _drive_smoke_run(
        tmp_path=sandbox_b,
        fixture_path=fixture_path,
        envelope_schema=envelope_schema,
        agents_dir=agents_dir,
    )
    assert "walking-skeleton-bundle" not in result_true.bundle_emitted_markers
    assert (
        "<!-- bmad-automation:marker walking-skeleton-bundle -->"
        not in result_true.bundle_text
    )
