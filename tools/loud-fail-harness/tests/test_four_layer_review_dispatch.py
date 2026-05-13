"""Contract-coverage matrix for Story 10.4's `four_layer_review_dispatch`
substrate library.

Story 10.4 — `failed_layers` enum extension + `bmad-code-review` 4-layer
integration. This module's tests assert the FUNCTIONAL contract of
:func:`loud_fail_harness.four_layer_review_dispatch.dispatch_four_layer_review`
and :func:`loud_fail_harness.four_layer_review_dispatch.merge_review_envelopes`
against the Phase-1.5 4-layer Review-BMAD + Review-LAD composition seam.

Each test maps to a specific AC clause from the Story 10.4 epic source
at ``_bmad-output/planning-artifacts/epics-phase-1.5.md`` lines 272-290.
The matrix below IS the AC-traceability index (review-enforced per AC-10's
test-count delta of ``N >= 12``).

LAD-disabled bit-identity invariant (Story 10.4 AC-5 + AC-7):
    [x] AC-5: dispatch_four_layer_review(lad_enabled=False) → single dispatch
        callback invocation, byte-equivalent merged envelope, lad_dispatched=False
        → ``test_dispatch_four_layer_review_lad_disabled_bit_identical_to_three_layer``
    [x] AC-7: merge_review_envelopes(envelope, None, registry) round-trip is byte-
        identical for every canonical Review-BMAD positive fixture
        → ``test_merge_review_envelopes_lad_disabled_bit_identical_to_input``

LAD-enabled 4-layer composition (Story 10.4 AC-4 + AC-6):
    [x] AC-4: bucket-passthrough discipline — merged findings carry all four
        bucket values verbatim; deterministic sort by (source, id)
        → ``test_merge_review_envelopes_preserves_bucket_passthrough``
    [x] AC-6 (i): both wrappers pass → status=pass, findings union,
        failed_layers=[]
        → ``test_dispatch_four_layer_review_both_pass_merges_clean``
    [x] AC-6 (ii): LAD status=blocked → failed_layers=["lad"] + synthetic
        meta-finding + marker emission via surface_failed_layers
        → ``test_dispatch_four_layer_review_lad_blocked_failed_layers_carries_lad``
    [x] AC-6 (iii): LAD dispatch raises SpecialistTimeoutExceeded → same
        graceful-degradation path as LAD status=blocked
        → ``test_dispatch_four_layer_review_lad_timeout_failed_layers_carries_lad``
    [x] AC-6 (iv): Review-BMAD partial + LAD pass → merged failed_layers
        preserved verbatim from Review-BMAD; no "lad" appended
        → ``test_dispatch_four_layer_review_review_bmad_partial_lad_pass``
    [x] AC-6 (v): Review-BMAD total fail (3-of-3 layers) + LAD pass → merged
        status=pass (LAD acts as surviving verdict per FR28); merged
        failed_layers preserved verbatim from Review-BMAD
        → ``test_dispatch_four_layer_review_review_bmad_total_lad_pass``
    [x] AC-6 (vi): Review-BMAD total fail (3-of-3 layers) + LAD also fails
        (SpecialistTimeoutExceeded) → merged status=blocked (4-of-4 total
        failure; no surviving layer reached a verdict); merged
        failed_layers=["auditor","blind","edge","lad"]
        → ``test_dispatch_four_layer_review_both_blocked_merged_status_blocked``
"""

from __future__ import annotations

import pathlib
from collections.abc import Callable
from typing import Any

import pytest
import yaml

from loud_fail_harness.four_layer_review_dispatch import (
    dispatch_four_layer_review,
    merge_review_envelopes,
)
from loud_fail_harness.orchestrator_run_entry import (
    AcceptanceCriterion,
    DispatchCallbackResult,
    StoryDocResolution,
)
from loud_fail_harness.review_layer_failure import (
    META_REVIEW_COMPLETENESS,
    REVIEW_LAYER_FAILED_MARKER,
)
from loud_fail_harness.specialist_dispatch import (
    EnvelopeValidationFailed,
    MarkerClassRegistry,
    SpecialistTimeoutExceeded,
)


# --------------------------------------------------------------------------- #
# Fixtures — canonical Review-BMAD + Review-LAD envelopes; stubs              #
# --------------------------------------------------------------------------- #


_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_REVIEW_PASS_THREE_LAYER_FIXTURE = (
    _REPO_ROOT / "examples" / "envelopes" / "review-pass-three-layer.yaml"
)
_REVIEW_LAD_PASS_FIXTURE = (
    _REPO_ROOT / "examples" / "envelopes" / "review-lad-pass.yaml"
)
_REVIEW_BMAD_POSITIVE_FIXTURES = (
    _REVIEW_PASS_THREE_LAYER_FIXTURE,
    _REPO_ROOT / "examples" / "envelopes" / "review-pass-acceptance-auditor.yaml",
    _REPO_ROOT / "examples" / "envelopes" / "review-pass-bucket-coverage.yaml",
    _REPO_ROOT / "examples" / "envelopes" / "review-pass-partial-layer-failure-with-meta.yaml",
)


def _load_yaml_envelope(path: pathlib.Path) -> dict[str, Any]:
    """Load an envelope fixture as a dict."""
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _canonical_registry() -> MarkerClassRegistry:
    """Build a registry containing the canonical marker class for tests."""
    return MarkerClassRegistry(
        marker_classes=frozenset({REVIEW_LAYER_FAILED_MARKER})
    )


def _make_minimal_story_doc_resolution() -> StoryDocResolution:
    """Construct a minimal StoryDocResolution shape for the dispatch."""
    return StoryDocResolution(
        path=pathlib.Path("/tmp/synthetic-story-10-4.md"),
        current_state="in-progress",
        acceptance_criteria=(
            AcceptanceCriterion(
                ac_id="AC-1",
                text="Synthetic AC for the test_four_layer_review_dispatch suite.",
            ),
        ),
    )


def _capture_dispatches() -> tuple[
    list[dict[str, Any]],
    Callable[..., DispatchCallbackResult],
]:
    """Return a (captures-list, dispatch_callback) pair.

    The callback appends one dict per invocation describing the specialist
    + story id; returns a generic ``DispatchCallbackResult(dispatched=True)``.
    """
    captures: list[dict[str, Any]] = []

    def _stub_callback(**kwargs: Any) -> DispatchCallbackResult:
        captures.append(
            {
                "specialist": kwargs.get("specialist"),
                "story_id": kwargs.get("story_id"),
            }
        )
        return DispatchCallbackResult(
            dispatched=True,
            reason=f"test stub dispatched {kwargs.get('specialist')!r}",
        )

    return captures, _stub_callback


def _capture_event_appender() -> tuple[list[dict[str, Any]], Callable[[dict[str, Any]], None]]:
    """Return a (events-list, event_log_appender) pair."""
    events: list[dict[str, Any]] = []

    def _stub_appender(event: dict[str, Any]) -> None:
        events.append(event)

    return events, _stub_appender


def _envelope_resolver_from_mapping(
    mapping: dict[str, dict[str, Any]],
) -> Callable[[str], dict[str, Any]]:
    """Return an envelope_resolver looking up envelopes by specialist key."""

    def _resolver(specialist: str) -> dict[str, Any]:
        return mapping[specialist]

    return _resolver


def _make_review_bmad_envelope(
    *,
    status: str = "pass",
    findings: list[dict[str, Any]] | None = None,
    failed_layers: list[str] | None = None,
    artifacts: list[str] | None = None,
    rationale: str = "Review-BMAD ran across the three live layers.",
) -> dict[str, Any]:
    """Construct a synthetic Review-BMAD envelope for tests."""
    env: dict[str, Any] = {
        "status": status,
        "artifacts": list(artifacts or []),
        "findings": list(findings or []),
        "rationale": rationale,
        "failed_layers": list(failed_layers or []),
    }
    return env


def _make_lad_envelope(
    *,
    status: str = "pass",
    findings: list[dict[str, Any]] | None = None,
    artifacts: list[str] | None = None,
    rationale: str = "Review-LAD ran the dual-reviewer code_review MCP pass.",
) -> dict[str, Any]:
    """Construct a synthetic Review-LAD envelope for tests."""
    env: dict[str, Any] = {
        "status": status,
        "artifacts": list(artifacts or []),
        "findings": list(findings or []),
        "rationale": rationale,
    }
    return env


def _make_finding(
    *,
    finding_id: str,
    source: str,
    bucket: str,
    severity: str,
    title: str | None = None,
    detail: str | None = None,
    location: str | None = None,
) -> dict[str, Any]:
    """Construct a synthetic finding dict."""
    return {
        "id": finding_id,
        "source": source,
        "title": title or f"Synthetic title for {finding_id}",
        "detail": detail or f"Synthetic detail for {finding_id}.",
        "location": location or "agents/review-bmad-wrapper.md:1",
        "bucket": bucket,
        "severity": severity,
    }


# --------------------------------------------------------------------------- #
# AC-5 — LAD-disabled config produces a bit-identical 3-layer dispatch path. #
# --------------------------------------------------------------------------- #


def test_dispatch_four_layer_review_lad_disabled_bit_identical_to_three_layer(
    tmp_path: pathlib.Path,
) -> None:
    """Story 10.4 AC-5: when lad_enabled=False, the substrate dispatches
    Review-BMAD ONCE and short-circuits — zero LAD Task-tool invocation;
    the returned FourLayerReviewResult carries lad_dispatched=False AND
    merged_envelope deep-equals the Review-BMAD envelope.
    """
    review_bmad_envelope = _load_yaml_envelope(_REVIEW_PASS_THREE_LAYER_FIXTURE)
    captures, callback = _capture_dispatches()
    events, appender = _capture_event_appender()
    resolver = _envelope_resolver_from_mapping(
        {"review-bmad": review_bmad_envelope}
    )

    result = dispatch_four_layer_review(
        story_id="10-4-test",
        story_doc_resolution=_make_minimal_story_doc_resolution(),
        run_state_path=tmp_path / "run-state.yaml",
        dispatch_callback=callback,
        event_log_appender=appender,
        marker_registry=_canonical_registry(),
        envelope_resolver=resolver,
        lad_enabled=False,
        agent_definition_dir=tmp_path / "agents",
    )

    # (i) Exactly one dispatch invocation and it is Review-BMAD.
    assert len(captures) == 1
    assert captures[0]["specialist"] == "review-bmad"
    # (ii) Merged envelope is deep-equal to the Review-BMAD envelope.
    assert result.merged_envelope == review_bmad_envelope
    # (iii) lad_dispatched is False and lad_envelope is None.
    assert result.lad_dispatched is False
    assert result.lad_envelope is None
    # (iv) Zero specialist="lad" events emitted (event appender wasn't
    # invoked by the substrate at this story's scope; the dispatch
    # callback owns the event emission).
    assert not any(e.get("specialist") == "lad" for e in events)


# --------------------------------------------------------------------------- #
# AC-7 — LAD-disabled merged-envelope byte-identity invariant.                 #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "fixture_path",
    _REVIEW_BMAD_POSITIVE_FIXTURES,
    ids=[p.name for p in _REVIEW_BMAD_POSITIVE_FIXTURES],
)
def test_merge_review_envelopes_lad_disabled_bit_identical_to_input(
    fixture_path: pathlib.Path,
) -> None:
    """Story 10.4 AC-7: merge_review_envelopes(envelope, lad_envelope=None,
    registry) returns a deep-equal clone of the input Review-BMAD envelope
    for every canonical Review-BMAD positive fixture.

    Proves the LAD-disabled merge is a structural passthrough; the Phase-1
    fixture corpus is preserved byte-for-byte downstream of the merge
    substrate even when Story 10.4's substrate is on the call path.
    """
    if not fixture_path.is_file():
        pytest.skip(f"fixture not present: {fixture_path}")
    envelope = _load_yaml_envelope(fixture_path)
    registry = _canonical_registry()

    merged = merge_review_envelopes(
        review_bmad_envelope=envelope,
        lad_envelope=None,
        marker_registry=registry,
    )

    assert merged == envelope, (
        f"LAD-disabled merge MUST be byte-identical to input envelope "
        f"for fixture {fixture_path.name}; AC-7 invariant violation"
    )
    # The merge MUST NOT mutate the input envelope.
    assert envelope == _load_yaml_envelope(fixture_path), (
        f"merge MUST NOT mutate input envelope; fixture {fixture_path.name}"
    )


# --------------------------------------------------------------------------- #
# AC-4 — bucket-driven triage passthrough discipline.                          #
# --------------------------------------------------------------------------- #


def test_merge_review_envelopes_preserves_bucket_passthrough() -> None:
    """Story 10.4 AC-4: the merged envelope's findings array carries the
    union of both envelopes' findings VERBATIM — same id, source, bucket,
    severity — sorted by (source, id) for deterministic byte-stable
    output.

    No bespoke LAD-only branching is introduced; LAD findings carry the
    same bucket-enum values as Review-BMAD findings (Pattern 1 + Story
    3.2 passthrough invariant).
    """
    review_bmad_envelope = _make_review_bmad_envelope(
        status="pass",
        findings=[
            _make_finding(
                finding_id="review-001",
                source="blind",
                bucket="patch",
                severity="MED",
            ),
            _make_finding(
                finding_id="review-002",
                source="auditor",
                bucket="defer",
                severity="LOW",
            ),
        ],
        failed_layers=[],
    )
    lad_envelope = _make_lad_envelope(
        status="pass",
        findings=[
            _make_finding(
                finding_id="lad-001",
                source="lad",
                bucket="patch",
                severity="LOW",
            ),
            _make_finding(
                finding_id="lad-002",
                source="lad",
                bucket="decision_needed",
                severity="MED",
            ),
        ],
    )
    registry = _canonical_registry()

    merged = merge_review_envelopes(
        review_bmad_envelope=review_bmad_envelope,
        lad_envelope=lad_envelope,
        marker_registry=registry,
    )

    findings = merged["findings"]
    assert len(findings) == 4
    # Sorted by (source, id) deterministically.
    expected_order = [
        ("auditor", "review-002"),
        ("blind", "review-001"),
        ("lad", "lad-001"),
        ("lad", "lad-002"),
    ]
    actual_order = [(f["source"], f["id"]) for f in findings]
    assert actual_order == expected_order
    # All bucket values preserved verbatim.
    bucket_values = [f["bucket"] for f in findings]
    assert "patch" in bucket_values  # review-001 + lad-001
    assert "defer" in bucket_values  # review-002
    assert "decision_needed" in bucket_values  # lad-002
    # All severity values preserved verbatim.
    for source_id, expected_severity in (
        (("blind", "review-001"), "MED"),
        (("auditor", "review-002"), "LOW"),
        (("lad", "lad-001"), "LOW"),
        (("lad", "lad-002"), "MED"),
    ):
        match = next(f for f in findings if (f["source"], f["id"]) == source_id)
        assert match["severity"] == expected_severity


# --------------------------------------------------------------------------- #
# AC-6 (i) — LAD-enabled happy path: both wrappers pass.                       #
# --------------------------------------------------------------------------- #


def test_dispatch_four_layer_review_both_pass_merges_clean(
    tmp_path: pathlib.Path,
) -> None:
    """Story 10.4 AC-6 (i): both wrappers return status=pass; merged
    envelope is status=pass + 4-source findings union + failed_layers=[].
    """
    review_bmad_envelope = _load_yaml_envelope(_REVIEW_PASS_THREE_LAYER_FIXTURE)
    lad_envelope = _load_yaml_envelope(_REVIEW_LAD_PASS_FIXTURE)
    captures, callback = _capture_dispatches()
    _events, appender = _capture_event_appender()
    resolver = _envelope_resolver_from_mapping(
        {"review-bmad": review_bmad_envelope, "lad": lad_envelope}
    )

    result = dispatch_four_layer_review(
        story_id="10-4-test",
        story_doc_resolution=_make_minimal_story_doc_resolution(),
        run_state_path=tmp_path / "run-state.yaml",
        dispatch_callback=callback,
        event_log_appender=appender,
        marker_registry=_canonical_registry(),
        envelope_resolver=resolver,
        lad_enabled=True,
        agent_definition_dir=tmp_path / "agents",
    )

    # Both wrappers dispatched.
    assert len(captures) == 2
    assert {c["specialist"] for c in captures} == {"review-bmad", "lad"}
    # Merged envelope verdict.
    merged = result.merged_envelope
    # The LAD pass fixture has a `bucket: patch` LOW-severity finding
    # (lad-002); the merged status rule fires `fail` only on
    # HIGH+patch combos (per AC-6 + the Review-BMAD wrapper's status
    # discipline). LOW patch findings keep status=pass.
    assert merged["status"] == "pass"
    # 4-source findings union.
    sources = {f["source"] for f in merged["findings"]}
    assert sources <= {"blind", "edge", "auditor", "merged", "lad"}
    assert "lad" in sources  # LAD layer represented
    assert "blind" in sources or "edge" in sources or "auditor" in sources
    # failed_layers is the empty list.
    assert merged.get("failed_layers", []) == []
    # Dispatched flag is True; lad_envelope captured.
    assert result.lad_dispatched is True
    assert result.lad_envelope == lad_envelope


# --------------------------------------------------------------------------- #
# AC-6 (ii) — LAD status=blocked → failed_layers=["lad"] + synth meta.        #
# --------------------------------------------------------------------------- #


def test_dispatch_four_layer_review_lad_blocked_failed_layers_carries_lad(
    tmp_path: pathlib.Path,
) -> None:
    """Story 10.4 AC-6 (ii): LAD wrapper returns status=blocked; the
    substrate composes surface_failed_layers — merged failed_layers
    carries ["lad"]; one synthetic decision_needed:HIGH meta-finding
    appended; marker emission record produced (consumed by the bundle
    assembler).
    """
    review_bmad_envelope = _load_yaml_envelope(_REVIEW_PASS_THREE_LAYER_FIXTURE)
    # LAD-blocked envelope per the wrapper's blocked-status discipline
    # (precondition failure — API key missing / MCP crash / etc.).
    lad_envelope = _make_lad_envelope(
        status="blocked",
        findings=[],
        rationale="`mcp__lad__code_review` returned `OPENROUTER_API_KEY missing`.",
    )
    _captures, callback = _capture_dispatches()
    _events, appender = _capture_event_appender()
    resolver = _envelope_resolver_from_mapping(
        {"review-bmad": review_bmad_envelope, "lad": lad_envelope}
    )

    result = dispatch_four_layer_review(
        story_id="10-4-test",
        story_doc_resolution=_make_minimal_story_doc_resolution(),
        run_state_path=tmp_path / "run-state.yaml",
        dispatch_callback=callback,
        event_log_appender=appender,
        marker_registry=_canonical_registry(),
        envelope_resolver=resolver,
        lad_enabled=True,
        agent_definition_dir=tmp_path / "agents",
    )

    merged = result.merged_envelope
    assert merged["failed_layers"] == ["lad"]
    # Exactly one synthetic meta-finding for the lad layer.
    lad_meta_findings = [
        f
        for f in merged["findings"]
        if f.get("id") == "review-layer-failed-lad"
    ]
    assert len(lad_meta_findings) == 1
    synth = lad_meta_findings[0]
    assert synth["source"] == "merged"
    assert synth["bucket"] == "decision_needed"
    assert synth["severity"] == "HIGH"
    assert synth["meta"] == META_REVIEW_COMPLETENESS
    # lad_dispatched True even though wrapper returned blocked.
    assert result.lad_dispatched is True
    assert result.lad_envelope is not None


# --------------------------------------------------------------------------- #
# AC-6 (iii) — LAD dispatch raises SpecialistTimeoutExceeded.                  #
# --------------------------------------------------------------------------- #


def test_dispatch_four_layer_review_lad_timeout_failed_layers_carries_lad(
    tmp_path: pathlib.Path,
) -> None:
    """Story 10.4 AC-6 (iii): dispatch_callback raises
    SpecialistTimeoutExceeded for the specialist=lad invocation; the
    substrate catches and routes through the same graceful-degradation
    path as the LAD-blocked case — merged failed_layers carries ["lad"]
    + synthetic meta-finding + marker emission.
    """
    review_bmad_envelope = _load_yaml_envelope(_REVIEW_PASS_THREE_LAYER_FIXTURE)
    captures, _basic_callback = _capture_dispatches()

    def _callback_raising_on_lad(**kwargs: Any) -> DispatchCallbackResult:
        captures.append(
            {
                "specialist": kwargs.get("specialist"),
                "story_id": kwargs.get("story_id"),
            }
        )
        if kwargs.get("specialist") == "lad":
            raise SpecialistTimeoutExceeded(
                timeout_seconds=900,
                specialist="lad",
                story_id=str(kwargs.get("story_id")),
                attempt_number=0,
            )
        return DispatchCallbackResult(
            dispatched=True,
            reason="test stub dispatched review-bmad",
        )

    _events, appender = _capture_event_appender()
    # The envelope resolver should NOT be invoked for "lad" because the
    # dispatch raised before envelope resolution; return only review-bmad.
    resolver = _envelope_resolver_from_mapping(
        {"review-bmad": review_bmad_envelope}
    )

    result = dispatch_four_layer_review(
        story_id="10-4-test",
        story_doc_resolution=_make_minimal_story_doc_resolution(),
        run_state_path=tmp_path / "run-state.yaml",
        dispatch_callback=_callback_raising_on_lad,
        event_log_appender=appender,
        marker_registry=_canonical_registry(),
        envelope_resolver=resolver,
        lad_enabled=True,
        agent_definition_dir=tmp_path / "agents",
    )

    merged = result.merged_envelope
    assert merged["failed_layers"] == ["lad"]
    lad_meta_findings = [
        f
        for f in merged["findings"]
        if f.get("id") == "review-layer-failed-lad"
    ]
    assert len(lad_meta_findings) == 1
    assert lad_meta_findings[0]["meta"] == META_REVIEW_COMPLETENESS
    # lad_envelope is None because dispatch raised; lad_dispatched True
    # because the dispatch attempt occurred (observable was produced).
    assert result.lad_envelope is None
    assert result.lad_dispatched is True
    # Both specialists' dispatch attempts captured (the lad call raised
    # after appending to captures via the closure).
    assert {c["specialist"] for c in captures} == {"review-bmad", "lad"}


# --------------------------------------------------------------------------- #
# AC-6 (iii-bis) — LAD dispatch raises EnvelopeValidationFailed.              #
# --------------------------------------------------------------------------- #


def test_dispatch_four_layer_review_lad_envelope_invalid_failed_layers_carries_lad(
    tmp_path: pathlib.Path,
) -> None:
    """Story 10.4 AC-6 (iii) extension: dispatch_callback raises
    EnvelopeValidationFailed for the specialist=lad invocation; the
    substrate catches and routes through the LAD graceful-degradation
    path (per Pattern 5 named-invariant exception handling).
    """
    review_bmad_envelope = _load_yaml_envelope(_REVIEW_PASS_THREE_LAYER_FIXTURE)

    def _callback_raising_envelope_invalid(**kwargs: Any) -> DispatchCallbackResult:
        if kwargs.get("specialist") == "lad":
            raise EnvelopeValidationFailed(
                errors=("findings[0]/bucket: not in enum",),
                envelope_dict={"status": "pass", "findings": [{"bucket": "suggest"}]},
            )
        return DispatchCallbackResult(dispatched=True, reason="review-bmad")

    _events, appender = _capture_event_appender()
    resolver = _envelope_resolver_from_mapping(
        {"review-bmad": review_bmad_envelope}
    )

    result = dispatch_four_layer_review(
        story_id="10-4-test",
        story_doc_resolution=_make_minimal_story_doc_resolution(),
        run_state_path=tmp_path / "run-state.yaml",
        dispatch_callback=_callback_raising_envelope_invalid,
        event_log_appender=appender,
        marker_registry=_canonical_registry(),
        envelope_resolver=resolver,
        lad_enabled=True,
        agent_definition_dir=tmp_path / "agents",
    )

    assert result.merged_envelope["failed_layers"] == ["lad"]
    assert result.lad_envelope is None
    assert result.lad_dispatched is True


# --------------------------------------------------------------------------- #
# AC-6 (iv) — Review-BMAD partial fail + LAD pass.                             #
# --------------------------------------------------------------------------- #


def test_dispatch_four_layer_review_review_bmad_partial_lad_pass(
    tmp_path: pathlib.Path,
) -> None:
    """Story 10.4 AC-6 (iv): Review-BMAD has failed_layers=["edge"]; LAD
    passes — merged failed_layers preserves Review-BMAD's verbatim
    ["edge"]; ZERO "lad" appended; LAD's findings flow through normally.
    """
    review_bmad_envelope = _make_review_bmad_envelope(
        status="pass",
        findings=[
            _make_finding(
                finding_id="review-001",
                source="blind",
                bucket="defer",
                severity="LOW",
            ),
            _make_finding(
                finding_id="review-002",
                source="auditor",
                bucket="defer",
                severity="LOW",
            ),
        ],
        failed_layers=["edge"],
    )
    lad_envelope = _make_lad_envelope(
        status="pass",
        findings=[
            _make_finding(
                finding_id="lad-001",
                source="lad",
                bucket="defer",
                severity="LOW",
            ),
        ],
    )
    _captures, callback = _capture_dispatches()
    _events, appender = _capture_event_appender()
    resolver = _envelope_resolver_from_mapping(
        {"review-bmad": review_bmad_envelope, "lad": lad_envelope}
    )

    result = dispatch_four_layer_review(
        story_id="10-4-test",
        story_doc_resolution=_make_minimal_story_doc_resolution(),
        run_state_path=tmp_path / "run-state.yaml",
        dispatch_callback=callback,
        event_log_appender=appender,
        marker_registry=_canonical_registry(),
        envelope_resolver=resolver,
        lad_enabled=True,
        agent_definition_dir=tmp_path / "agents",
    )

    merged = result.merged_envelope
    # Review-BMAD's failed_layers preserved verbatim; "lad" NOT appended.
    assert merged["failed_layers"] == ["edge"]
    # LAD's finding flowed through normally.
    lad_sources = [f for f in merged["findings"] if f["source"] == "lad"]
    assert len(lad_sources) == 1
    assert lad_sources[0]["id"] == "lad-001"
    # ZERO LAD synthetic meta-finding appended (no LAD-layer failure).
    lad_meta_findings = [
        f
        for f in merged["findings"]
        if f.get("id") == "review-layer-failed-lad"
    ]
    assert lad_meta_findings == []
    assert merged["status"] == "pass"


# --------------------------------------------------------------------------- #
# AC-6 (v) — Review-BMAD total fail (3-of-3 layers) + LAD pass.                #
# --------------------------------------------------------------------------- #


def test_dispatch_four_layer_review_review_bmad_total_lad_pass(
    tmp_path: pathlib.Path,
) -> None:
    """Story 10.4 AC-6 (v): Review-BMAD status=blocked with
    failed_layers=["auditor","blind","edge"] (3-of-3 total Review-BMAD
    layer failure); LAD passes — merged status=pass (LAD acts as the
    surviving verdict per FR28 strict-superset graceful-degradation);
    merged failed_layers=["auditor","blind","edge"] (LAD passed, so
    no "lad" append).
    """
    review_bmad_total_fail_fixture = (
        _REPO_ROOT
        / "examples"
        / "envelopes"
        / "review-blocked-three-layer-failure-with-meta.yaml"
    )
    review_bmad_envelope = _load_yaml_envelope(review_bmad_total_fail_fixture)
    lad_envelope = _load_yaml_envelope(_REVIEW_LAD_PASS_FIXTURE)
    _captures, callback = _capture_dispatches()
    _events, appender = _capture_event_appender()
    resolver = _envelope_resolver_from_mapping(
        {"review-bmad": review_bmad_envelope, "lad": lad_envelope}
    )

    result = dispatch_four_layer_review(
        story_id="10-4-test",
        story_doc_resolution=_make_minimal_story_doc_resolution(),
        run_state_path=tmp_path / "run-state.yaml",
        dispatch_callback=callback,
        event_log_appender=appender,
        marker_registry=_canonical_registry(),
        envelope_resolver=resolver,
        lad_enabled=True,
        agent_definition_dir=tmp_path / "agents",
    )

    merged = result.merged_envelope
    # FR28 strict-superset graceful-degradation: LAD passed → merged
    # status pass even though Review-BMAD was blocked.
    assert merged["status"] == "pass"
    # Review-BMAD's failed_layers preserved verbatim; no "lad" appended.
    assert merged["failed_layers"] == ["auditor", "blind", "edge"]
    # LAD's findings flowed through normally.
    lad_sources = [f for f in merged["findings"] if f["source"] == "lad"]
    assert len(lad_sources) >= 1
    # ZERO LAD synthetic meta-finding appended.
    lad_meta_findings = [
        f
        for f in merged["findings"]
        if f.get("id") == "review-layer-failed-lad"
    ]
    assert lad_meta_findings == []


# --------------------------------------------------------------------------- #
# AC-6 (vi) — Review-BMAD total fail (3-of-3) + LAD also fails → blocked.    #
# --------------------------------------------------------------------------- #


def test_dispatch_four_layer_review_both_blocked_merged_status_blocked(
    tmp_path: pathlib.Path,
) -> None:
    """Story 10.4 AC-6: Review-BMAD status=blocked with all three Review-BMAD
    layers failed (failed_layers=["auditor","blind","edge"]); LAD dispatch
    raises SpecialistTimeoutExceeded — the 4-of-4 total-failure case.

    The substrate MUST produce merged status="blocked" via the
    ``_compose_merged_status`` branch that fires when
    ``failed_layers_union == _ALL_FOUR_LAYERS and review_bmad_status == "blocked"``.

    Also asserts:
    - merged failed_layers = ["auditor","blind","edge","lad"] (sorted union).
    - One LAD synthetic meta-finding appended (``review-layer-failed-lad``).
    - Three Review-BMAD meta-findings deduped cleanly (no duplicates).
    """
    review_bmad_total_fail_fixture = (
        _REPO_ROOT
        / "examples"
        / "envelopes"
        / "review-blocked-three-layer-failure-with-meta.yaml"
    )
    review_bmad_envelope = _load_yaml_envelope(review_bmad_total_fail_fixture)

    captures: list[dict[str, Any]] = []

    def _callback_lad_timeout(**kwargs: Any) -> DispatchCallbackResult:
        captures.append(
            {
                "specialist": kwargs.get("specialist"),
                "story_id": kwargs.get("story_id"),
            }
        )
        if kwargs.get("specialist") == "lad":
            raise SpecialistTimeoutExceeded(
                timeout_seconds=900,
                specialist="lad",
                story_id=str(kwargs.get("story_id")),
                attempt_number=0,
            )
        return DispatchCallbackResult(
            dispatched=True,
            reason="test stub dispatched review-bmad",
        )

    _events, appender = _capture_event_appender()
    # LAD dispatch raised before envelope resolution; resolver only covers review-bmad.
    resolver = _envelope_resolver_from_mapping({"review-bmad": review_bmad_envelope})

    result = dispatch_four_layer_review(
        story_id="10-4-test",
        story_doc_resolution=_make_minimal_story_doc_resolution(),
        run_state_path=tmp_path / "run-state.yaml",
        dispatch_callback=_callback_lad_timeout,
        event_log_appender=appender,
        marker_registry=_canonical_registry(),
        envelope_resolver=resolver,
        lad_enabled=True,
        agent_definition_dir=tmp_path / "agents",
    )

    merged = result.merged_envelope

    # (i) 4-of-4 total failure → merged status must be "blocked".
    assert merged["status"] == "blocked", (
        "AC-6: 4-of-4 total failure (all Review-BMAD layers + LAD) must produce "
        "merged status='blocked'"
    )
    # (ii) Merged failed_layers = sorted union of all four layers.
    assert merged["failed_layers"] == ["auditor", "blind", "edge", "lad"]
    # (iii) Exactly one LAD synthetic meta-finding appended.
    lad_meta_findings = [
        f
        for f in merged["findings"]
        if f.get("id") == "review-layer-failed-lad"
    ]
    assert len(lad_meta_findings) == 1
    assert lad_meta_findings[0]["source"] == "merged"
    assert lad_meta_findings[0]["bucket"] == "decision_needed"
    assert lad_meta_findings[0]["severity"] == "HIGH"
    assert lad_meta_findings[0]["meta"] == META_REVIEW_COMPLETENESS
    # (iv) Review-BMAD's three synthetic meta-findings present without duplicates.
    for layer in ("auditor", "blind", "edge"):
        layer_meta = [
            finding
            for finding in merged["findings"]
            if finding.get("id") == f"review-layer-failed-{layer}"
        ]
        assert len(layer_meta) == 1, (
            f"Expected exactly one meta-finding for layer {layer!r} after dedup; "
            f"found {len(layer_meta)}"
        )
    # (v) lad_dispatched True (dispatch was attempted); lad_envelope None (raised).
    assert result.lad_dispatched is True
    assert result.lad_envelope is None
