"""Contract-coverage matrix for the FR33 runtime reconciliation gate (story 6.8).

This docstring IS the contract-coverage checklist required by AC-4 (parallel
to story 1.8's AC-6 review-enforced matrix). Reviewers verify every row maps
to at least one passing test in this module. The matrix is review-enforced,
NOT CI-enforced (parallel to story 1.2 / 1.3 / 1.4 / 1.5 / 1.6 / 1.7 / 1.8
AC-5/6).

Pure-API skip-event extraction (AC-1, AC-3):
    [x] (a) extract_runtime_skip_events filters non-skip events           → test_extract_runtime_skip_events_filters_non_skip
    [x] (a) extract_runtime_skip_events returns SkipEvents per skip-class  → test_extract_runtime_skip_events_returns_skip_events
    [x] (a) extract_runtime_skip_events routes shape-broken to bucket     → test_extract_runtime_skip_events_shape_broken_routed
    [x] (a) extract_runtime_skip_events captures emission_site map        → test_extract_runtime_skip_events_emission_site_capture

Pure-API marker extraction (AC-1):
    [x] (b) extract_runtime_markers strips Pattern 2 sub-classification    → test_extract_runtime_markers_strips_sub_classification
    [x] (b) extract_runtime_markers routes unknown taxonomy to bucket     → test_extract_runtime_markers_unknown_taxonomy_routed
    [x] (b) extract_runtime_markers builds Markers for known taxonomy     → test_extract_runtime_markers_known_taxonomy

Replay against committed capture fixtures (AC-3, AC-4):
    [x] (c) replay_runtime_capture against `clean/` reconciles cleanly     → test_replay_runtime_capture_clean_passes
    [x] (d) replay_runtime_capture against `missing-emission/` produces  AC-2 finding → test_replay_runtime_capture_missing_emission_finding

Aggregation + sorted-output discipline (AC-1, AC-3):
    [x] (e) run_fr33_runtime_gate aggregates two captures + sort-stable    → test_run_fr33_runtime_gate_aggregates_clean_and_missing

Distinct-shape diagnostics (AC-2):
    [x] (f) format_findings carries `## Runtime reconciliation findings` header → test_format_findings_runtime_header
    [x] (f) format_findings does NOT contain fixture-gate template substring → test_format_findings_distinct_from_fixture_gate
    [x] (f) format_findings carries the AC-2 verbatim template            → test_format_findings_carries_ac2_verbatim_template

CLI / main exit-code matrix (AC-1, AC-7):
    [x] (g) main with no positional args defaults to glob path           → test_main_default_glob_resolves_clean_passes
    [x] (g) main with explicit positional captures uses supplied paths   → test_main_explicit_positional_captures
    [x] (h) main exits 0 on clean fixture                                → test_main_exits_zero_on_clean
    [x] (h) main exits 1 on missing-emission                             → test_main_exits_one_on_missing_emission
    [x] (h) main exits 2 on schema-shape-broken                          → test_main_exits_two_on_schema_shape_broken
    [x] (h) main exits 2 on marker-taxonomy-mismatch                     → test_main_exits_two_on_taxonomy_mismatch
    [x] (h) main with --help resolves to argparse                        → test_main_help_resolves

Shared-reconciler invariant (AC-1):
    [x] (i) fr33_runtime_gate.reconcile is reconciler.reconcile (same callable)  → test_shared_reconciler_invariant_runtime_imports_canonical
    [x] (i) fr33_fixture_gate.reconcile is reconciler.reconcile (same callable)  → test_shared_reconciler_invariant_fixture_imports_canonical
    [x] (i) Both gates' reconcile references are SAME object (load-bearing)      → test_shared_reconciler_invariant_both_gates_same_callable

Loud-fail / harness-level errors (AC-7, Pattern 5):
    [x] missing captures-root → exit 2 + named path                       → test_loud_fail_on_missing_captures_root
    [x] missing taxonomy file → exit 2                                    → test_loud_fail_on_missing_taxonomy
    [x] missing event-schema → exit 2                                     → test_loud_fail_on_missing_event_schema
"""

from __future__ import annotations

import io
import json
import pathlib
import sys
from typing import Any

import pytest
import yaml

from loud_fail_harness import fr33_fixture_gate, fr33_runtime_gate, reconciler
from loud_fail_harness.fr33_runtime_gate import (
    RuntimeFinding,
    RuntimeGateResult,
    RuntimeReference,
    RuntimeReplaySource,
    extract_runtime_markers,
    extract_runtime_skip_events,
    format_findings,
    main,
    replay_runtime_capture,
    run_fr33_runtime_gate,
)
# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _fixtures_root() -> pathlib.Path:
    """Resolve the committed happy-path runtime-captures fixture root.

    Per AC-7: this directory's contents are the default-glob target for the
    CI step; every capture in it must reconcile cleanly so CI exits 0 on a
    green build. Known-failure captures live under
    :func:`_failure_cases_root`.
    """
    return pathlib.Path(__file__).parent / "fixtures" / "runtime-captures"


def _failure_cases_root() -> pathlib.Path:
    """Resolve the sibling known-failure capture corpus.

    Captures here are committed but NOT default-globbed by the CI step —
    referenced explicitly by unit tests. The split keeps AC-7's "CI step
    exits 0 on green build" requirement clean while preserving Story 6.8's
    "missing-emission gate exits 1" invariant for unit tests.
    """
    return (
        pathlib.Path(__file__).parent
        / "fixtures"
        / "runtime-captures-failure-cases"
    )


def _load_canonical_event_schema() -> dict:
    """Load the on-disk canonical orchestrator-event schema for tests."""
    from loud_fail_harness._shared import find_repo_root, load_schema

    return load_schema(find_repo_root() / "schemas" / "orchestrator-event.yaml")


def _load_canonical_taxonomy() -> set[str]:
    """Load the on-disk canonical marker-taxonomy for tests."""
    from loud_fail_harness._shared import find_repo_root

    return reconciler.load_marker_taxonomy(
        find_repo_root() / "schemas" / "marker-taxonomy.yaml"
    )


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


def _make_capture(
    tmp_path: pathlib.Path,
    *,
    name: str,
    events: list[dict[str, Any]],
    active_markers: list[str],
    story_id: str = "tmp-runtime-replay",
    schema_version: str = "1.3",
    extra_run_state: dict | None = None,
) -> pathlib.Path:
    """Build a tmp capture directory under ``tmp_path/<name>``."""
    capture = tmp_path / name
    capture.mkdir()
    events_lines = [json.dumps(e) for e in events]
    (capture / "events.jsonl").write_text(
        "\n".join(events_lines) + "\n", encoding="utf-8"
    )
    run_state: dict = {
        "schema_version": schema_version,
        "story_id": story_id,
        "run_id": f"run-{story_id}-001",
        "current_state": "done",
        "branch_name": f"story/{story_id}",
        "dispatched_specialist": None,
        "last_envelope": None,
        "retry_history": [],
        "active_markers": active_markers,
        "cost_to_date_by_specialist": {},
        "pending_qa_dispatch_payload": None,
    }
    if extra_run_state:
        run_state.update(extra_run_state)
    (capture / "run-state.yaml").write_text(
        yaml.safe_dump(run_state, sort_keys=False), encoding="utf-8"
    )
    return capture


def _skip_event_entry(
    *,
    story_id: str,
    marker_class: str,
    emission_site: str | None = None,
    event_id: str | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "event_class": "specialist-returned",
        "event_id": event_id or f"ev-{marker_class}-1",
        "timestamp": "2026-04-26T00:00:00Z",
        "story_id": story_id,
        "marker_class": marker_class,
    }
    if emission_site is not None:
        entry["emission_site"] = emission_site
    return entry


# ---------------------------------------------------------------------------
# Pure-API skip-event extraction (AC-1, AC-3)
# ---------------------------------------------------------------------------


def test_extract_runtime_skip_events_filters_non_skip() -> None:
    """(a) Non-skip event entries (no `marker_class` field) are filtered out."""
    events = [
        {
            "event_class": "state-transition",
            "event_id": "ev-1",
            "timestamp": "2026-04-26T00:00:00Z",
            "story_id": "s",
            "from_state": "ready-for-dev",
            "to_state": "in-progress",
        },
        {
            "event_class": "specialist-dispatched",
            "event_id": "ev-2",
            "timestamp": "2026-04-26T00:01:00Z",
            "story_id": "s",
            "specialist": "dev",
            "prompt_id": "p",
            "retry_attempt": 0,
        },
    ]
    skip_events, findings, sites = extract_runtime_skip_events(
        events, event_schema={}, file_path="events.jsonl"
    )
    assert skip_events == []
    assert findings == []
    assert sites == {}


def test_extract_runtime_skip_events_returns_skip_events() -> None:
    """(a) Entries carrying `marker_class` produce SkipEvents per skip-class."""
    events = [
        _skip_event_entry(story_id="s", marker_class="LAD-skipped"),
        _skip_event_entry(story_id="s", marker_class="Tier-3-not-configured"),
    ]
    skip_events, findings, sites = extract_runtime_skip_events(
        events, event_schema={}, file_path="events.jsonl"
    )
    assert findings == []
    assert len(skip_events) == 2
    assert {s.marker_class for s in skip_events} == {
        "LAD-skipped",
        "Tier-3-not-configured",
    }
    assert all(s.story_id == "s" for s in skip_events)
    assert all(s.source == RuntimeReplaySource for s in skip_events)


def test_extract_runtime_skip_events_shape_broken_routed() -> None:
    """(a) Entries failing shape validation route to schema-shape-broken
    findings (NOT silent_skips — AC-2 specification per (iv))."""
    events = [
        # Missing event_id, timestamp, story_id — three required-field violations.
        {"event_class": "specialist-returned"},
        # Valid skip event for control.
        _skip_event_entry(story_id="s", marker_class="LAD-skipped"),
    ]
    skip_events, findings, _ = extract_runtime_skip_events(
        events, event_schema={}, file_path="events.jsonl"
    )
    assert len(skip_events) == 1
    assert skip_events[0].marker_class == "LAD-skipped"
    assert len(findings) == 1
    assert findings[0].category == "schema-shape-broken"
    assert "shape-broken" in findings[0].message


def test_extract_runtime_skip_events_emission_site_capture() -> None:
    """(a) The optional `emission_site` field is captured into the returned
    map, keyed by (marker_class, story_id). When absent, the map carries
    the documented unknown-surface sentinel value."""
    events = [
        _skip_event_entry(
            story_id="s", marker_class="LAD-skipped", emission_site="agents/lad.md:7"
        ),
        _skip_event_entry(
            story_id="s", marker_class="Tier-3-not-configured"
        ),  # no emission_site
    ]
    _, _, sites = extract_runtime_skip_events(
        events, event_schema={}, file_path="events.jsonl"
    )
    assert sites[("LAD-skipped", "s")] == "agents/lad.md:7"
    # missing emission_site → sentinel value populates the map; the
    # rendered diagnostic substitutes the documented annotation pointing
    # at architecture.md § Runtime gate input contract.
    assert sites[("Tier-3-not-configured", "s")] == "<unknown-surface>"


# ---------------------------------------------------------------------------
# Pure-API marker extraction (AC-1)
# ---------------------------------------------------------------------------


def test_extract_runtime_markers_strips_sub_classification() -> None:
    """(b) Pattern 2 `<base-class>: <sub-classification>` parser strips suffix.
    The matching key in reconcile is base-class only per Story 1.4."""
    taxonomy = {"dangling-evidence-ref"}
    markers, findings = extract_runtime_markers(
        ("dangling-evidence-ref: qa-evidence",),
        story_id="s",
        taxonomy=taxonomy,
        file_path="run-state.yaml",
    )
    assert findings == []
    assert len(markers) == 1
    assert markers[0].marker_class == "dangling-evidence-ref"
    assert markers[0].story_id == "s"


def test_extract_runtime_markers_unknown_taxonomy_routed() -> None:
    """(b) Markers whose base-class is NOT in the taxonomy route to
    marker-taxonomy-mismatch findings (loud-fail per NFR-O5)."""
    taxonomy = {"LAD-skipped"}
    markers, findings = extract_runtime_markers(
        ("not-a-real-class",),
        story_id="s",
        taxonomy=taxonomy,
        file_path="run-state.yaml",
    )
    assert markers == []
    assert len(findings) == 1
    assert findings[0].category == "marker-taxonomy-mismatch"
    assert findings[0].marker_class == "not-a-real-class"


def test_extract_runtime_markers_known_taxonomy() -> None:
    """(b) Known-taxonomy markers construct Marker instances cleanly."""
    taxonomy = {"LAD-skipped", "Tier-3-not-configured"}
    markers, findings = extract_runtime_markers(
        ("LAD-skipped", "Tier-3-not-configured"),
        story_id="s",
        taxonomy=taxonomy,
        file_path="run-state.yaml",
    )
    assert findings == []
    assert {m.marker_class for m in markers} == {
        "LAD-skipped",
        "Tier-3-not-configured",
    }
    assert all(m.source == RuntimeReplaySource for m in markers)


# ---------------------------------------------------------------------------
# Replay against committed capture fixtures (AC-3, AC-4)
# ---------------------------------------------------------------------------


def test_replay_runtime_capture_clean_passes() -> None:
    """(c) replay_runtime_capture against `clean/` returns three finding lists
    empty AND a passing list with the matched-pair count."""
    taxonomy = _load_canonical_taxonomy()
    schema = _load_canonical_event_schema()
    capture = _fixtures_root() / "clean"
    result = replay_runtime_capture(
        capture / "events.jsonl",
        capture / "run-state.yaml",
        taxonomy,
        schema,
    )
    assert len(result.passing) == 2
    assert result.runtime_reconciliation_mismatch == []
    assert result.schema_shape_broken == []
    assert result.marker_taxonomy_mismatch == []
    passing_classes = {ref.marker_class for ref in result.passing}
    assert passing_classes == {"LAD-skipped", "Tier-3-not-configured"}


def test_replay_runtime_capture_missing_emission_finding() -> None:
    """(d) replay_runtime_capture against `missing-emission/` returns ONE
    runtime-reconciliation-mismatch finding carrying the AC-2 verbatim
    template + the missing skip-event class + the captured code-surface
    substring."""
    taxonomy = _load_canonical_taxonomy()
    schema = _load_canonical_event_schema()
    capture = _failure_cases_root() / "missing-emission"
    result = replay_runtime_capture(
        capture / "events.jsonl",
        capture / "run-state.yaml",
        taxonomy,
        schema,
    )
    assert len(result.passing) == 1
    assert result.passing[0].marker_class == "LAD-skipped"
    assert len(result.runtime_reconciliation_mismatch) == 1
    finding = result.runtime_reconciliation_mismatch[0]
    assert finding.marker_class == "Tier-3-not-configured"
    assert (
        "Runtime reconciliation failed: reference-project run produced "
        "skip-event class `Tier-3-not-configured`"
    ) in finding.message
    assert "qa_evidence_tier.py:354" in finding.message
    assert (
        "Inspect specialist or hook at "
        "`tools/loud-fail-harness/src/loud_fail_harness/qa_evidence_tier.py:354`"
        " for missing emission."
    ) in finding.message
    assert result.schema_shape_broken == []
    assert result.marker_taxonomy_mismatch == []


# ---------------------------------------------------------------------------
# Aggregation + sorted-output discipline (AC-1, AC-3)
# ---------------------------------------------------------------------------


def test_run_fr33_runtime_gate_aggregates_clean_and_missing() -> None:
    """(e) run_fr33_runtime_gate over the BOTH-corpus union (clean/ +
    missing-emission/) preserves the four-bucket partitioning AND sorted-
    output discipline (lex-sort on (file_path, marker_class) per Story 1.8
    precedent)."""
    taxonomy = _load_canonical_taxonomy()
    schema = _load_canonical_event_schema()
    captures = [
        _fixtures_root() / "clean",
        _failure_cases_root() / "missing-emission",
    ]
    result = run_fr33_runtime_gate(
        captures, taxonomy, schema, captures_root=_fixtures_root()
    )
    # clean/ contributes 2 passing; missing-emission/ contributes 1 passing
    # + 1 reconciliation-mismatch.
    assert len(result.passing) == 3
    assert len(result.runtime_reconciliation_mismatch) == 1
    assert result.schema_shape_broken == []
    assert result.marker_taxonomy_mismatch == []
    # Sort-stability: the passing list is sorted by (file_path, marker_class).
    keys = [(r.file_path, r.marker_class) for r in result.passing]
    assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# Distinct-shape diagnostics (AC-2)
# ---------------------------------------------------------------------------


def test_format_findings_runtime_header() -> None:
    """(f) format_findings's CI output carries the NEW
    `## Runtime reconciliation findings` section header per AC-2's
    distinct-shape diagnostics commitment."""
    finding = RuntimeFinding(
        file_path="events.jsonl",
        marker_class="Tier-3-not-configured",
        category="runtime-reconciliation-mismatch",
        message="Runtime reconciliation failed: ...",
        remediation="(per AC-2; ...)",
    )
    result = RuntimeGateResult(
        passing=[],
        runtime_reconciliation_mismatch=[finding],
        schema_shape_broken=[],
        marker_taxonomy_mismatch=[],
    )
    rendered = format_findings(
        result, captures_root="captures/", taxonomy_path="schemas/marker-taxonomy.yaml"
    )
    assert "## Runtime reconciliation findings" in rendered


def test_format_findings_distinct_from_fixture_gate() -> None:
    """(f) format_findings's CI output does NOT contain the fixture-gate's
    `Fixture reconciliation failed: synthetic-story` substring per AC-2's
    "their failure signatures are inspectable separately" commitment."""
    finding = RuntimeFinding(
        file_path="events.jsonl",
        marker_class="Tier-3-not-configured",
        category="runtime-reconciliation-mismatch",
        message=(
            "Runtime reconciliation failed: reference-project run "
            "produced skip-event class `Tier-3-not-configured` at code "
            "surface `s.py:1` but no emitted marker reconciled. Inspect "
            "specialist or hook at `s.py:1` for missing emission."
        ),
        remediation="(per AC-2)",
    )
    result = RuntimeGateResult(
        passing=[],
        runtime_reconciliation_mismatch=[finding],
        schema_shape_broken=[],
        marker_taxonomy_mismatch=[],
    )
    rendered = format_findings(
        result, captures_root="captures/", taxonomy_path="t.yaml"
    )
    assert "Fixture reconciliation failed: synthetic-story" not in rendered


def test_format_findings_carries_ac2_verbatim_template() -> None:
    """(f) The AC-2 verbatim template substring is preserved end-to-end:
    `Runtime reconciliation failed: reference-project run produced
    skip-event class `<X>` at code surface `<surface>` but no emitted
    marker reconciled.`"""
    taxonomy = _load_canonical_taxonomy()
    schema = _load_canonical_event_schema()
    capture = _failure_cases_root() / "missing-emission"
    result = replay_runtime_capture(
        capture / "events.jsonl",
        capture / "run-state.yaml",
        taxonomy,
        schema,
    )
    rendered = format_findings(
        result, captures_root="captures/", taxonomy_path="t.yaml"
    )
    assert "Runtime reconciliation failed: reference-project run produced" in rendered
    assert "skip-event class `Tier-3-not-configured`" in rendered
    assert "but no emitted marker reconciled." in rendered
    assert "Inspect specialist or hook at" in rendered


# ---------------------------------------------------------------------------
# CLI / main exit-code matrix (AC-1, AC-7)
# ---------------------------------------------------------------------------


def test_main_default_glob_resolves_clean_passes() -> None:
    """(g) main with no positional args defaults to globbing
    tests/fixtures/runtime-captures/*/. Passing the canonical happy-path
    corpus root via --captures-root yields exit 0 (no failures committed
    in the default-glob target per AC-7's CI-step contract)."""
    rc, out, _ = _capture_main(
        ["--captures-root", str(_fixtures_root())]
    )
    assert rc == 0, f"unexpected rc; out={out!r}"
    assert "FR33 runtime reconciliation gate (story 6.8)" in out
    assert "2 passing capture entry(s) reconciled cleanly" in out


def test_main_default_glob_failure_corpus_exit_one() -> None:
    """(g) main against the failure-case corpus root produces exit 1 with
    the AC-2 reconciliation-mismatch diagnostic. Witnesses that the failure
    case captures are committed and discoverable; the AC-7 CI-step
    invariant is preserved by living OUTSIDE the default-glob target."""
    rc, out, _ = _capture_main(
        ["--captures-root", str(_failure_cases_root())]
    )
    assert rc == 1, f"unexpected rc; out={out!r}"
    assert "1 runtime-reconciliation-mismatch finding(s)" in out


def test_main_explicit_positional_captures(tmp_path: pathlib.Path) -> None:
    """(g) main with explicit positional captures uses the supplied paths
    rather than globbing the default root."""
    capture = _make_capture(
        tmp_path,
        name="ad-hoc",
        events=[
            _skip_event_entry(
                story_id="ad-hoc",
                marker_class="LAD-skipped",
                emission_site="x.py:1",
            ),
        ],
        active_markers=["LAD-skipped"],
        story_id="ad-hoc",
    )
    rc, out, _ = _capture_main([str(capture)])
    assert rc == 0, f"unexpected rc; out={out!r}"
    assert "1 passing capture entry(s) reconciled cleanly" in out


def test_main_exits_zero_on_clean() -> None:
    """(h) Clean fixture only → exit 0."""
    rc, out, _ = _capture_main([str(_fixtures_root() / "clean")])
    assert rc == 0, f"unexpected rc; out={out!r}"


def test_main_exits_one_on_missing_emission() -> None:
    """(h) missing-emission fixture only → exit 1."""
    rc, out, _ = _capture_main(
        [str(_failure_cases_root() / "missing-emission")]
    )
    assert rc == 1, f"unexpected rc; out={out!r}"
    assert "runtime-reconciliation-mismatch" in out


def test_main_exits_two_on_schema_shape_broken(tmp_path: pathlib.Path) -> None:
    """(h) Capture with shape-broken events.jsonl entry → exit 2."""
    capture = tmp_path / "broken"
    capture.mkdir()
    # Invalid JSON line + valid skip-event line.
    (capture / "events.jsonl").write_text(
        "this is not json\n"
        + json.dumps(
            _skip_event_entry(
                story_id="s",
                marker_class="LAD-skipped",
                emission_site="x.py:1",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (capture / "run-state.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.3",
                "story_id": "s",
                "run_id": "r",
                "current_state": "done",
                "branch_name": "b",
                "dispatched_specialist": None,
                "last_envelope": None,
                "retry_history": [],
                "active_markers": ["LAD-skipped"],
                "cost_to_date_by_specialist": {},
                "pending_qa_dispatch_payload": None,
            }
        ),
        encoding="utf-8",
    )
    rc, out, _ = _capture_main([str(capture)])
    assert rc == 2, f"unexpected rc; out={out!r}"
    assert "schema-shape-broken" in out


def test_main_exits_two_on_taxonomy_mismatch(tmp_path: pathlib.Path) -> None:
    """(h) Capture with a non-taxonomy marker-class in active_markers → exit 2."""
    capture = _make_capture(
        tmp_path,
        name="taxonomy-mismatch",
        events=[
            _skip_event_entry(
                story_id="taxonomy-mismatch",
                marker_class="LAD-skipped",
                emission_site="x.py:1",
            )
        ],
        active_markers=["not-a-real-marker-class"],
        story_id="taxonomy-mismatch",
    )
    rc, out, _ = _capture_main([str(capture)])
    assert rc == 2, f"unexpected rc; out={out!r}"
    assert "marker-taxonomy-mismatch" in out


def test_main_help_resolves() -> None:
    """(h) main --help resolves to argparse and exits 0."""
    with pytest.raises(SystemExit) as exc_info:
        _capture_main(["--help"])
    assert exc_info.value.code == 0


# ---------------------------------------------------------------------------
# Shared-reconciler invariant (AC-1)
# ---------------------------------------------------------------------------


def test_shared_reconciler_invariant_runtime_imports_canonical() -> None:
    """(i) The runtime gate's `reconcile` symbol IS the canonical
    `reconciler.reconcile` (not a shadowed copy)."""
    assert fr33_runtime_gate.reconcile is reconciler.reconcile


def test_shared_reconciler_invariant_fixture_imports_canonical() -> None:
    """(i) The fixture gate's `reconcile` symbol IS the canonical
    `reconciler.reconcile` (not a shadowed copy)."""
    assert fr33_fixture_gate.reconcile is reconciler.reconcile


def test_shared_reconciler_invariant_both_gates_same_callable() -> None:
    """(i) BOTH gates reference the SAME `reconcile` callable — load-bearing
    for AC-1's "share the reconciler component without logic duplication"
    commitment. Prevents a future contributor from accidentally branching
    the reconciliation logic per Story 1.8 AC-4 + Story 6.8 AC-1."""
    assert fr33_runtime_gate.reconcile is fr33_fixture_gate.reconcile


# ---------------------------------------------------------------------------
# Loud-fail / harness-level errors (AC-7, Pattern 5)
# ---------------------------------------------------------------------------


def test_loud_fail_on_missing_captures_root(tmp_path: pathlib.Path) -> None:
    """Missing captures-root → exit 2 + named path in stderr."""
    missing_root = tmp_path / "does-not-exist"
    rc, _, err = _capture_main(["--captures-root", str(missing_root)])
    assert rc == 2
    assert "runtime-captures root unreadable" in err
    assert str(missing_root) in err


def test_loud_fail_on_missing_taxonomy(tmp_path: pathlib.Path) -> None:
    """Missing taxonomy file → exit 2 (named path in stderr)."""
    missing_tax = tmp_path / "no-taxonomy.yaml"
    rc, _, err = _capture_main(
        [
            "--taxonomy-path", str(missing_tax),
            str(_fixtures_root() / "clean"),
        ]
    )
    assert rc == 2
    assert "marker-taxonomy" in err


def test_loud_fail_on_missing_event_schema(tmp_path: pathlib.Path) -> None:
    """Missing event-schema → exit 2 (named path in stderr)."""
    missing_schema = tmp_path / "no-schema.yaml"
    rc, _, err = _capture_main(
        [
            "--event-schema", str(missing_schema),
            str(_fixtures_root() / "clean"),
        ]
    )
    assert rc == 2
    assert "orchestrator-event schema" in err


# ---------------------------------------------------------------------------
# Pydantic v2 frozen-model discipline (parallel to story 1.8's matrix)
# ---------------------------------------------------------------------------


def test_runtime_finding_is_frozen() -> None:
    f = RuntimeFinding(
        file_path="x",
        marker_class="x",
        category="schema-shape-broken",
        message="x",
        remediation="x",
    )
    with pytest.raises(Exception):
        f.message = "mutated"  # type: ignore[misc]


def test_runtime_reference_is_frozen() -> None:
    r = RuntimeReference(file_path="x", marker_class="x")
    with pytest.raises(Exception):
        r.marker_class = "mutated"  # type: ignore[misc]


def test_runtime_gate_result_is_frozen() -> None:
    result = RuntimeGateResult(
        passing=[],
        runtime_reconciliation_mismatch=[],
        schema_shape_broken=[],
        marker_taxonomy_mismatch=[],
    )
    with pytest.raises(Exception):
        result.passing = []  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Reconciler-input contract (negative test — empty events.jsonl case)
# ---------------------------------------------------------------------------


def test_replay_runtime_capture_empty_events_no_findings(
    tmp_path: pathlib.Path,
) -> None:
    """An events.jsonl with only non-skip entries + an empty active_markers
    list reconciles cleanly (no skip-events; no markers; no findings).
    Sanity check that the gate's clean-baseline path is exercised."""
    capture = _make_capture(
        tmp_path,
        name="empty",
        events=[
            {
                "event_class": "state-transition",
                "event_id": "ev-1",
                "timestamp": "2026-04-26T00:00:00Z",
                "story_id": "empty",
                "from_state": "ready-for-dev",
                "to_state": "in-progress",
            }
        ],
        active_markers=[],
        story_id="empty",
    )
    taxonomy = _load_canonical_taxonomy()
    schema = _load_canonical_event_schema()
    result = replay_runtime_capture(
        capture / "events.jsonl",
        capture / "run-state.yaml",
        taxonomy,
        schema,
    )
    assert result.passing == []
    assert result.runtime_reconciliation_mismatch == []
    assert result.schema_shape_broken == []
    assert result.marker_taxonomy_mismatch == []
