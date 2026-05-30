"""Contract-coverage matrix for the FR33 fixture-driven reconciliation gate (story 1.8).

This docstring IS the contract-coverage checklist required by AC-6. Reviewers
verify every row maps to at least one passing test in this module. The matrix
is review-enforced, NOT CI-enforced (parallel to story 1.2 / 1.3 / 1.4 / 1.5
/ 1.6 / 1.7 AC-5/6).

Pure-API classification cases (AC-2, AC-3, AC-5):
    [x] per-fixture pass — synthetic 3-class corpus            → test_per_fixture_pass_synthetic
    [x] reconciliation_mismatch — silent_skips populated       → test_reconciliation_mismatch_silent_skips
    [x] reconciliation_mismatch — orphan_markers populated     → test_reconciliation_mismatch_orphan_markers
    [x] reconciliation_mismatch — wrong-class matched pair     → test_reconciliation_mismatch_wrong_class_matched
    [x] reconciliation_mismatch — matched=[] zero matches      → test_reconciliation_mismatch_zero_matches
    [x] dangling_event_class — declared not in enum            → test_dangling_event_class
    [x] harness_bug — synthesized payload fails schema         → test_harness_bug_synthesized_payload_invalid
    [x] harness_bug schema validation produces ALL errors      → test_schema_validation_produces_all_errors_per_fixture
    [x] mixed-precedence — harness-bug + reconciliation-mismatch → test_mixed_precedence_harness_bug_wins
    [x] PR introduces reconciler regression (epic AC #2)       → test_pr_introduces_reconciler_regression
    [x] event_class default = specialist-returned, status fail → test_event_class_default_specialist_returned
    [x] event_class override = env-provisioned                 → test_event_class_override_env_provisioned
    [x] empty corpus → no findings + exit 0                    → test_empty_corpus_no_findings
    [x] subdirectory fixture (expected_marker=None) → harness_bug → test_subdirectory_fixture_produces_harness_bug
    [x] shape-breaking fixture (expected_marker=None) → harness_bug → test_shape_broken_fixture_produces_harness_bug
    [x] per-class required-field synthesis covers all 9 enum   → test_per_class_required_field_synthesis

Determinism (AC-2 last clause + AC-6):
    [x] run_fr33_fixture_gate is byte-identical across runs    → test_findings_deterministic
    [x] GateResult.model_dump_json byte-identical              → test_gate_result_json_serialization_stable
    [x] _synthesize_event byte-identical (no uuid4 / now)      → test_synthesize_event_deterministic

Pydantic v2 frozen-model discipline:
    [x] ReplayFinding is frozen (assignment raises)            → test_replay_finding_is_frozen
    [x] Reference is frozen (assignment raises)                → test_reference_is_frozen
    [x] GateResult is frozen (assignment raises)               → test_gate_result_is_frozen

CLI / main exit-code matrix (AC-4, AC-6):
    [x] canonical corpus validates → exit 0 + 27 Summary line  → test_canonical_corpus_validates
    [x] main exits 1 on dangling_event_class                   → test_main_exits_one_on_dangling_event_class
    [x] main --help resolves to argparse                       → test_main_help_resolves
    [x] main with no flags resolves canonical files            → test_main_with_no_flags_resolves_canonical_files

Loud-fail / harness-level errors (AC-4, AC-6, Pattern 5):
    [x] missing fixtures-dir → exit 2 + named path             → test_loud_fail_on_missing_fixtures_dir
    [x] missing taxonomy file → exit 2                         → test_loud_fail_on_missing_taxonomy
    [x] missing event-schema → exit 2                          → test_loud_fail_on_missing_event_schema
    [x] malformed event-schema → exit 2                        → test_loud_fail_on_malformed_event_schema
    [x] malformed taxonomy YAML → exit 2                       → test_loud_fail_on_malformed_taxonomy

Coverage (AC-6):
    [x] fr33_fixture_gate.py module-level statement coverage ≥ 90% → review-enforced; not a CI gate
"""

from __future__ import annotations

import io
import pathlib
import sys
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from loud_fail_harness import fr33_fixture_gate
from loud_fail_harness.fixture_coverage import Fixture
from loud_fail_harness.fr33_fixture_gate import (
    GateResult,
    Reference,
    ReplayFinding,
    _CANONICAL_EVENT_CLASS_ENUM,
    _synthesize_event,
    main,
    run_fr33_fixture_gate,
)
from loud_fail_harness.reconciler import (
    ClassificationResult,
    Marker,
    MatchedPair,
    SkipEvent,
)

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _write_taxonomy(path: pathlib.Path, classes: list[str]) -> None:
    """Write a minimal valid marker-taxonomy.yaml at ``path``."""
    entries = [
        {
            "marker_class": c,
            "diagnostic_pointer": "synthetic test entry",
            "sub_classifications": [],
        }
        for c in classes
    ]
    payload = {"schema_version": "1.0", "markers": entries}
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")


def _write_fixture(
    path: pathlib.Path,
    *,
    expected_marker: str | None = None,
    scenario: str | None = "synthetic scenario",
    extra: dict | None = None,
    raw_content: str | None = None,
    body: str = "# body\n",
) -> None:
    if raw_content is not None:
        path.write_text(raw_content, encoding="utf-8")
        return
    fm: dict[str, Any] = {}
    if expected_marker is not None:
        fm["expected_marker"] = expected_marker
    if scenario is not None:
        fm["scenario"] = scenario
    if extra:
        fm.update(extra)
    text = "---\n" + yaml.safe_dump(fm) + "---\n" + body
    path.write_text(text, encoding="utf-8")


def _make_corpus(
    tmp_path: pathlib.Path,
    *,
    fixtures: dict[str, dict],
    include_readme: bool = False,
) -> pathlib.Path:
    corpus = tmp_path / "synthetic-stories"
    corpus.mkdir()
    for filename, kwargs in fixtures.items():
        _write_fixture(corpus / filename, **kwargs)
    if include_readme:
        (corpus / "README.md").write_text("# README\n", encoding="utf-8")
    return corpus


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


def _load_canonical_event_schema() -> dict:
    """Load the on-disk canonical orchestrator-event schema for tests."""
    from loud_fail_harness._shared import find_repo_root, load_schema

    return load_schema(find_repo_root() / "schemas" / "orchestrator-event.yaml")


def _make_taxonomy_set(classes: list[str]) -> set[str]:
    return set(classes)


def _make_synthetic_corpus_with_fixtures(
    tmp_path: pathlib.Path,
    *,
    fixtures_map: dict[str, dict],
    taxonomy_classes: list[str],
) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
    """Build a tmp corpus + tmp taxonomy + share canonical event-schema path.

    Returns (fixtures_dir, taxonomy_path, event_schema_path).
    """
    from loud_fail_harness._shared import find_repo_root

    corpus = _make_corpus(tmp_path, fixtures=fixtures_map)
    taxonomy = tmp_path / "marker-taxonomy.yaml"
    _write_taxonomy(taxonomy, taxonomy_classes)
    event_schema = find_repo_root() / "schemas" / "orchestrator-event.yaml"
    return corpus, taxonomy, event_schema


# ---------------------------------------------------------------------------
# Pure-API classification cases (AC-2, AC-3, AC-5)
# ---------------------------------------------------------------------------


def test_per_fixture_pass_synthetic(tmp_path: pathlib.Path) -> None:
    """N=3 synthetic taxonomy + 3 fixtures → passing == 3, others empty."""
    corpus, taxonomy_path, event_schema_path = _make_synthetic_corpus_with_fixtures(
        tmp_path,
        fixtures_map={
            "alpha.md": {"expected_marker": "alpha"},
            "beta.md": {"expected_marker": "beta"},
            "gamma.md": {"expected_marker": "gamma"},
        },
        taxonomy_classes=["alpha", "beta", "gamma"],
    )
    rc, out, err = _capture_main(
        [
            "--fixtures-dir", str(corpus),
            "--taxonomy-path", str(taxonomy_path),
            "--event-schema", str(event_schema_path),
        ]
    )
    assert rc == 0, f"stdout: {out}\nstderr: {err}"
    assert "3 passing fixture(s)" in out
    assert "0 reconciliation-mismatch" in out
    assert "0 harness-bug" in out
    assert "0 dangling-event-class" in out


def test_reconciliation_mismatch_silent_skips(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Monkeypatch reconcile to leave skips silent → reconciliation_mismatch."""
    corpus, taxonomy_path, event_schema_path = _make_synthetic_corpus_with_fixtures(
        tmp_path,
        fixtures_map={"alpha.md": {"expected_marker": "alpha"}},
        taxonomy_classes=["alpha"],
    )

    def fake_reconcile(
        skips: list[SkipEvent], markers: list[Marker]
    ) -> ClassificationResult:
        return ClassificationResult(
            matched=[], silent_skips=skips, orphan_markers=[]
        )

    monkeypatch.setattr(fr33_fixture_gate, "reconcile", fake_reconcile)

    rc, out, _ = _capture_main(
        [
            "--fixtures-dir", str(corpus),
            "--taxonomy-path", str(taxonomy_path),
            "--event-schema", str(event_schema_path),
        ]
    )
    assert rc == 1
    assert "Fixture reconciliation failed" in out
    assert "synthetic-story 'alpha'" in out
    assert "expected_marker 'alpha'" in out
    assert "silent_skips=[alpha]" in out
    assert "matched=[]" in out
    assert "Inspect harness logic or fixture declaration" in out


def test_reconciliation_mismatch_orphan_markers(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Monkeypatch reconcile to leave markers orphaned → reconciliation_mismatch."""
    corpus, taxonomy_path, event_schema_path = _make_synthetic_corpus_with_fixtures(
        tmp_path,
        fixtures_map={"alpha.md": {"expected_marker": "alpha"}},
        taxonomy_classes=["alpha"],
    )

    def fake_reconcile(
        skips: list[SkipEvent], markers: list[Marker]
    ) -> ClassificationResult:
        return ClassificationResult(
            matched=[], silent_skips=[], orphan_markers=markers
        )

    monkeypatch.setattr(fr33_fixture_gate, "reconcile", fake_reconcile)

    rc, out, _ = _capture_main(
        [
            "--fixtures-dir", str(corpus),
            "--taxonomy-path", str(taxonomy_path),
            "--event-schema", str(event_schema_path),
        ]
    )
    assert rc == 1
    assert "orphan_markers=[alpha]" in out
    assert "matched=[]" in out


def test_reconciliation_mismatch_wrong_class_matched(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Monkeypatch reconcile to return a mismatched-class pair."""
    corpus, taxonomy_path, event_schema_path = _make_synthetic_corpus_with_fixtures(
        tmp_path,
        fixtures_map={"foo.md": {"expected_marker": "foo"}},
        taxonomy_classes=["foo", "bar"],
    )

    def fake_reconcile(
        skips: list[SkipEvent], markers: list[Marker]
    ) -> ClassificationResult:
        bad_skip = SkipEvent(marker_class="bar", story_id="x", source="t")
        bad_marker = Marker(marker_class="bar", story_id="x", source="t")
        return ClassificationResult(
            matched=[MatchedPair(skip_event=bad_skip, marker=bad_marker)],
            silent_skips=[],
            orphan_markers=[],
        )

    monkeypatch.setattr(fr33_fixture_gate, "reconcile", fake_reconcile)

    rc, out, _ = _capture_main(
        [
            "--fixtures-dir", str(corpus),
            "--taxonomy-path", str(taxonomy_path),
            "--event-schema", str(event_schema_path),
        ]
    )
    assert rc == 1
    assert "matched=[(bar, bar)] (different marker class)" in out


def test_reconciliation_mismatch_zero_matches(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Monkeypatch reconcile to return all-empty result → matched=[] (zero matches)."""
    corpus, taxonomy_path, event_schema_path = _make_synthetic_corpus_with_fixtures(
        tmp_path,
        fixtures_map={"alpha.md": {"expected_marker": "alpha"}},
        taxonomy_classes=["alpha"],
    )

    def fake_reconcile(
        skips: list[SkipEvent], markers: list[Marker]
    ) -> ClassificationResult:
        return ClassificationResult(
            matched=[], silent_skips=[], orphan_markers=[]
        )

    monkeypatch.setattr(fr33_fixture_gate, "reconcile", fake_reconcile)

    rc, out, _ = _capture_main(
        [
            "--fixtures-dir", str(corpus),
            "--taxonomy-path", str(taxonomy_path),
            "--event-schema", str(event_schema_path),
        ]
    )
    assert rc == 1
    assert "matched=[] (zero matches)" in out


def test_dangling_event_class(tmp_path: pathlib.Path) -> None:
    """Fixture with expected_event_class not in canonical enum → dangling_event_class finding."""
    corpus, taxonomy_path, event_schema_path = _make_synthetic_corpus_with_fixtures(
        tmp_path,
        fixtures_map={
            "rogue.md": {
                "expected_marker": "rogue",
                "extra": {"expected_event_class": "not-in-schema-enum"},
            },
        },
        taxonomy_classes=["rogue"],
    )
    rc, out, _ = _capture_main(
        [
            "--fixtures-dir", str(corpus),
            "--taxonomy-path", str(taxonomy_path),
            "--event-schema", str(event_schema_path),
        ]
    )
    assert rc == 1
    assert "Fixture event-class declaration invalid" in out
    assert "synthetic-story 'rogue'" in out
    assert "'not-in-schema-enum'" in out
    # canonical enum must be named verbatim in the diagnostic
    for canonical in _CANONICAL_EVENT_CLASS_ENUM:
        assert canonical in out
    assert "FR65" in out  # remediation pointer references the workflow


def test_harness_bug_synthesized_payload_invalid(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Monkeypatch _synthesize_event to drop event_id → harness_bug exit 2."""
    corpus, taxonomy_path, event_schema_path = _make_synthetic_corpus_with_fixtures(
        tmp_path,
        fixtures_map={"alpha.md": {"expected_marker": "alpha"}},
        taxonomy_classes=["alpha"],
    )

    def broken_synthesize(
        fixture: Fixture,
        parsed_frontmatter: Any,
        *,
        event_class_enum: Any = _CANONICAL_EVENT_CLASS_ENUM,
    ) -> tuple[dict | None, ReplayFinding | None]:
        return (
            {
                # missing event_id deliberately
                "event_class": "specialist-returned",
                "timestamp": "2026-04-26T00:00:00Z",
                "story_id": "1.8-replay-alpha",
                "specialist": "dev",
                "prompt_id": "p",
                "retry_attempt": 0,
                "status": "fail",
            },
            None,
        )

    monkeypatch.setattr(fr33_fixture_gate, "_synthesize_event", broken_synthesize)

    rc, out, _ = _capture_main(
        [
            "--fixtures-dir", str(corpus),
            "--taxonomy-path", str(taxonomy_path),
            "--event-schema", str(event_schema_path),
        ]
    )
    assert rc == 2
    assert "Harness bug" in out
    assert "synthetic-story 'alpha'" in out
    assert "event_id" in out  # the format_errors output names the missing field


def test_schema_validation_produces_all_errors_per_fixture(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A payload missing TWO required fields surfaces BOTH errors verbatim."""
    corpus, taxonomy_path, event_schema_path = _make_synthetic_corpus_with_fixtures(
        tmp_path,
        fixtures_map={"alpha.md": {"expected_marker": "alpha"}},
        taxonomy_classes=["alpha"],
    )

    def doubly_broken(
        fixture: Fixture,
        parsed_frontmatter: Any,
        *,
        event_class_enum: Any = _CANONICAL_EVENT_CLASS_ENUM,
    ) -> tuple[dict | None, ReplayFinding | None]:
        # missing event_id AND timestamp deliberately
        return (
            {
                "event_class": "specialist-returned",
                "story_id": "1.8-replay-alpha",
                "specialist": "dev",
                "prompt_id": "p",
                "retry_attempt": 0,
                "status": "fail",
            },
            None,
        )

    monkeypatch.setattr(fr33_fixture_gate, "_synthesize_event", doubly_broken)

    rc, out, _ = _capture_main(
        [
            "--fixtures-dir", str(corpus),
            "--taxonomy-path", str(taxonomy_path),
            "--event-schema", str(event_schema_path),
        ]
    )
    assert rc == 2
    # both missing-required errors must appear in the diagnostic prose
    assert "event_id" in out
    assert "timestamp" in out


def test_mixed_precedence_harness_bug_wins(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mix harness-bug (one fixture) + reconciliation-mismatch (other) → exit 2; both findings printed."""
    corpus, taxonomy_path, event_schema_path = _make_synthetic_corpus_with_fixtures(
        tmp_path,
        fixtures_map={
            "alpha.md": {"expected_marker": "alpha"},
            "beta.md": {"expected_marker": "beta"},
        },
        taxonomy_classes=["alpha", "beta"],
    )

    real_synthesize = fr33_fixture_gate._synthesize_event

    def selective_synthesize(
        fixture: Fixture,
        parsed_frontmatter: Any,
        *,
        event_class_enum: Any = _CANONICAL_EVENT_CLASS_ENUM,
    ) -> tuple[dict | None, ReplayFinding | None]:
        if "alpha" in fixture.file_path:
            # broken payload for alpha
            return (
                {
                    "event_class": "specialist-returned",
                    # missing event_id
                    "timestamp": "2026-04-26T00:00:00Z",
                    "story_id": "1.8-replay-alpha",
                    "specialist": "dev",
                    "prompt_id": "p",
                    "retry_attempt": 0,
                    "status": "fail",
                },
                None,
            )
        return real_synthesize(
            fixture, parsed_frontmatter, event_class_enum=event_class_enum
        )

    real_reconcile = fr33_fixture_gate.reconcile

    def selective_reconcile(
        skips: list[SkipEvent], markers: list[Marker]
    ) -> ClassificationResult:
        # Force a reconciliation mismatch for beta only
        if any("beta" in s.story_id or "" for s in skips):
            return ClassificationResult(
                matched=[], silent_skips=skips, orphan_markers=[]
            )
        return real_reconcile(skips, markers)

    monkeypatch.setattr(fr33_fixture_gate, "_synthesize_event", selective_synthesize)
    monkeypatch.setattr(fr33_fixture_gate, "reconcile", selective_reconcile)

    rc, out, _ = _capture_main(
        [
            "--fixtures-dir", str(corpus),
            "--taxonomy-path", str(taxonomy_path),
            "--event-schema", str(event_schema_path),
        ]
    )
    # harness-bug wins on exit code
    assert rc == 2
    # but BOTH categories' diagnostics appear in stdout (precedence affects exit code only)
    assert "Harness bug" in out
    assert "Fixture reconciliation failed" in out


def test_pr_introduces_reconciler_regression(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Epic AC #2: PR regresses reconciler → ALL 27 fixtures hit reconciliation_mismatch."""

    def regressed_reconcile(
        skips: list[SkipEvent], markers: list[Marker]
    ) -> ClassificationResult:
        return ClassificationResult(
            matched=[], silent_skips=skips, orphan_markers=[]
        )

    monkeypatch.setattr(fr33_fixture_gate, "reconcile", regressed_reconcile)

    rc, out, _ = _capture_main([])
    assert rc == 1
    assert "30 reconciliation-mismatch finding(s)" in out
    # Spot-check that several canonical fixtures appear
    for fixture_stem in (
        "heuristic-skipped",
        "LAD-skipped",
        "Tier-3-not-configured",
        "env-setup-failed",
    ):
        assert fixture_stem in out


def test_event_class_default_specialist_returned(tmp_path: pathlib.Path) -> None:
    """Fixture with NO expected_event_class → synthesized event_class=specialist-returned, status=fail; payload validates."""
    corpus, taxonomy_path, event_schema_path = _make_synthetic_corpus_with_fixtures(
        tmp_path,
        fixtures_map={"heuristic.md": {"expected_marker": "heuristic"}},
        taxonomy_classes=["heuristic"],
    )
    # Run the gate end-to-end; success implies the synthesized payload validated
    rc, out, _ = _capture_main(
        [
            "--fixtures-dir", str(corpus),
            "--taxonomy-path", str(taxonomy_path),
            "--event-schema", str(event_schema_path),
        ]
    )
    assert rc == 0
    assert "1 passing fixture(s)" in out

    # And the unit-level synthesizer produces the expected event_class
    fixture = Fixture(
        file_path="heuristic.md",
        expected_marker="heuristic",
        frontmatter_findings=[],
    )
    payload, finding = _synthesize_event(fixture, {"expected_marker": "heuristic"})
    assert finding is None
    assert payload is not None
    assert payload["event_class"] == "specialist-returned"
    assert payload["status"] == "fail"


def test_event_class_override_env_provisioned(tmp_path: pathlib.Path) -> None:
    """Fixture with expected_event_class: env-provisioned → synthesized event_class=env-provisioned; payload validates."""
    corpus, taxonomy_path, event_schema_path = _make_synthetic_corpus_with_fixtures(
        tmp_path,
        fixtures_map={
            "envfail.md": {
                "expected_marker": "env-setup-failed",
                "extra": {"expected_event_class": "env-provisioned"},
            },
        },
        taxonomy_classes=["env-setup-failed"],
    )
    rc, out, _ = _capture_main(
        [
            "--fixtures-dir", str(corpus),
            "--taxonomy-path", str(taxonomy_path),
            "--event-schema", str(event_schema_path),
        ]
    )
    assert rc == 0
    assert "1 passing fixture(s)" in out

    # Unit-level: confirm synthesizer honors the override
    fixture = Fixture(
        file_path="envfail.md",
        expected_marker="env-setup-failed",
        frontmatter_findings=[],
    )
    payload, finding = _synthesize_event(
        fixture,
        {"expected_marker": "env-setup-failed", "expected_event_class": "env-provisioned"},
    )
    assert finding is None
    assert payload is not None
    assert payload["event_class"] == "env-provisioned"


def test_empty_corpus_no_findings(tmp_path: pathlib.Path) -> None:
    """Empty corpus → exit 0 (intentionally distinct from story 1.7's loud-fail empty path).

    The seam contract: 1.7 enforces COVERAGE (every taxonomy class needs a
    fixture); 1.8 enforces RECONCILIATION-OF-COVERED. Nothing to reconcile
    is a valid pass for THIS gate; 1.7's gate runs UPSTREAM and catches the
    coverage failure.
    """
    corpus, taxonomy_path, event_schema_path = _make_synthetic_corpus_with_fixtures(
        tmp_path,
        fixtures_map={},  # empty
        taxonomy_classes=["alpha"],
    )
    # Add README so the corpus dir isn't empty; mirrors story 1.7's discipline
    (corpus / "README.md").write_text("# README\n", encoding="utf-8")
    rc, out, _ = _capture_main(
        [
            "--fixtures-dir", str(corpus),
            "--taxonomy-path", str(taxonomy_path),
            "--event-schema", str(event_schema_path),
        ]
    )
    assert rc == 0
    assert "0 passing fixture(s)" in out
    assert "0 reconciliation-mismatch" in out


def test_subdirectory_fixture_produces_harness_bug(tmp_path: pathlib.Path) -> None:
    """Fixture inside a subdirectory → expected_marker=None → harness_bug per AC-3 'NEVER as silent passes'."""
    corpus, taxonomy_path, event_schema_path = _make_synthetic_corpus_with_fixtures(
        tmp_path,
        fixtures_map={"alpha.md": {"expected_marker": "alpha"}},
        taxonomy_classes=["alpha"],
    )
    nested = corpus / "nested"
    nested.mkdir()
    _write_fixture(nested / "deep.md", expected_marker="alpha")

    rc, out, _ = _capture_main(
        [
            "--fixtures-dir", str(corpus),
            "--taxonomy-path", str(taxonomy_path),
            "--event-schema", str(event_schema_path),
        ]
    )
    # alpha.md passes; nested/deep.md has expected_marker=None (shape-broken by
    # story 1.7's contract) → harness_bug; exit 2 (mixed-precedence)
    assert rc == 2
    assert "1 passing fixture(s)" in out
    assert "1 harness-bug finding(s)" in out
    assert "Harness bug" in out


def test_shape_broken_fixture_produces_harness_bug(tmp_path: pathlib.Path) -> None:
    """Fixture with expected_marker=None (no frontmatter at all) → harness_bug per AC-3.
    Fixture missing 'scenario' but with valid expected_marker → still passes reconciliation
    (this gate only cares about expected_marker; shape validation belongs to story 1.7)."""
    corpus, taxonomy_path, event_schema_path = _make_synthetic_corpus_with_fixtures(
        tmp_path,
        fixtures_map={
            # missing scenario; expected_marker still parses → reconciliation passes
            "alpha.md": {"expected_marker": "alpha", "scenario": None},
        },
        taxonomy_classes=["alpha"],
    )
    # Fully-broken fixture (no frontmatter) → expected_marker=None → harness_bug
    _write_fixture(
        corpus / "broken.md",
        raw_content="no frontmatter at all\n",
    )
    rc, out, _ = _capture_main(
        [
            "--fixtures-dir", str(corpus),
            "--taxonomy-path", str(taxonomy_path),
            "--event-schema", str(event_schema_path),
        ]
    )
    # alpha passes reconciliation; broken.md has expected_marker=None → harness_bug
    assert rc == 2
    assert "1 passing fixture(s)" in out
    assert "1 harness-bug finding(s)" in out
    assert "Harness bug" in out
    assert "broken" in out


def test_per_class_required_field_synthesis() -> None:
    """For each of the 9 canonical event_class enum values, _synthesize_event produces a payload that validates."""
    from loud_fail_harness.event_validator import validate_event

    schema = _load_canonical_event_schema()

    for event_class in _CANONICAL_EVENT_CLASS_ENUM:
        fixture = Fixture(
            file_path=f"{event_class}.md",
            expected_marker="test-marker",
            frontmatter_findings=[],
        )
        payload, finding = _synthesize_event(
            fixture,
            {"expected_marker": "test-marker", "expected_event_class": event_class},
        )
        assert finding is None, f"unexpected finding for {event_class}"
        assert payload is not None, f"no payload synthesized for {event_class}"
        assert payload["event_class"] == event_class
        errors = validate_event(payload, schema)
        assert errors == [], (
            f"payload for {event_class} failed schema validation: "
            f"{[str(e) for e in errors]}"
        )


# ---------------------------------------------------------------------------
# Determinism (AC-2 last clause + AC-6)
# ---------------------------------------------------------------------------


def test_findings_deterministic(tmp_path: pathlib.Path) -> None:
    """Two invocations on the same input produce identical GateResult."""
    from loud_fail_harness._shared import load_schema
    from loud_fail_harness.fixture_coverage import discover_fixtures
    from loud_fail_harness.reconciler import load_marker_taxonomy

    corpus, taxonomy_path, event_schema_path = _make_synthetic_corpus_with_fixtures(
        tmp_path,
        fixtures_map={
            "alpha.md": {"expected_marker": "alpha"},
            "beta.md": {"expected_marker": "beta"},
            "gamma.md": {"expected_marker": "gamma"},
        },
        taxonomy_classes=["alpha", "beta", "gamma"],
    )
    fixtures = discover_fixtures(corpus)
    taxonomy = load_marker_taxonomy(taxonomy_path)
    event_schema = load_schema(event_schema_path)

    r1 = run_fr33_fixture_gate(fixtures, taxonomy, event_schema, fixtures_dir=corpus)
    r2 = run_fr33_fixture_gate(fixtures, taxonomy, event_schema, fixtures_dir=corpus)
    assert r1 == r2


def test_gate_result_json_serialization_stable(tmp_path: pathlib.Path) -> None:
    """GateResult.model_dump_json() is byte-identical across two invocations."""
    from loud_fail_harness._shared import load_schema
    from loud_fail_harness.fixture_coverage import discover_fixtures
    from loud_fail_harness.reconciler import load_marker_taxonomy

    corpus, taxonomy_path, event_schema_path = _make_synthetic_corpus_with_fixtures(
        tmp_path,
        fixtures_map={
            "alpha.md": {"expected_marker": "alpha"},
            "beta.md": {"expected_marker": "beta"},
        },
        taxonomy_classes=["alpha", "beta"],
    )
    fixtures = discover_fixtures(corpus)
    taxonomy = load_marker_taxonomy(taxonomy_path)
    event_schema = load_schema(event_schema_path)

    r1 = run_fr33_fixture_gate(fixtures, taxonomy, event_schema, fixtures_dir=corpus)
    r2 = run_fr33_fixture_gate(fixtures, taxonomy, event_schema, fixtures_dir=corpus)
    assert r1.model_dump_json() == r2.model_dump_json()


def test_synthesize_event_deterministic() -> None:
    """_synthesize_event byte-equal across two invocations on same fixture."""
    fixture = Fixture(
        file_path="examples/synthetic-stories/heuristic-skipped.md",
        expected_marker="heuristic-skipped",
        frontmatter_findings=[],
    )
    parsed = {"expected_marker": "heuristic-skipped", "scenario": "x"}
    p1, f1 = _synthesize_event(fixture, parsed)
    p2, f2 = _synthesize_event(fixture, parsed)
    assert f1 is None and f2 is None
    assert p1 == p2
    # No uuid4 / datetime.now: timestamp is the literal canonical value
    assert p1 is not None
    assert p1["timestamp"] == "2026-04-26T00:00:00Z"
    assert p1["event_id"] == "ev-1-8-replay-heuristic-skipped"
    assert p1["story_id"] == "1.8-replay-heuristic-skipped"


# ---------------------------------------------------------------------------
# Pydantic v2 frozen-model discipline
# ---------------------------------------------------------------------------


def test_replay_finding_is_frozen() -> None:
    f = ReplayFinding(
        file_path="x.md",
        marker_class="x",
        category="harness-bug",
        message="m",
        remediation="r",
    )
    with pytest.raises(ValidationError):
        f.message = "mutated"  # type: ignore[misc]


def test_reference_is_frozen() -> None:
    r = Reference(file_path="x.md", marker_class="x")
    with pytest.raises(ValidationError):
        r.marker_class = "y"  # type: ignore[misc]


def test_gate_result_is_frozen() -> None:
    g = GateResult(
        passing=[],
        reconciliation_mismatch=[],
        harness_bug=[],
        dangling_event_class=[],
    )
    with pytest.raises(ValidationError):
        g.passing = []  # type: ignore[misc]


# ---------------------------------------------------------------------------
# CLI / main exit-code matrix (AC-4, AC-6)
# ---------------------------------------------------------------------------


def test_canonical_corpus_validates() -> None:
    """The canonical 30-fixture corpus + canonical schemas → exit 0 (story
    2.3 added 2 markers + 2 fixtures (27 → 29); story 14.3 added 1 marker
    + 1 fixture (29 → 30))."""
    rc, out, err = _capture_main([])
    assert rc == 0, f"stdout: {out}\nstderr: {err}"
    assert "Summary: 30 passing fixture(s)" in out
    assert "0 reconciliation-mismatch finding(s)" in out
    assert "0 harness-bug finding(s)" in out
    assert "0 dangling-event-class finding(s)" in out


def test_main_exits_one_on_dangling_event_class(tmp_path: pathlib.Path) -> None:
    corpus, taxonomy_path, event_schema_path = _make_synthetic_corpus_with_fixtures(
        tmp_path,
        fixtures_map={
            "alpha.md": {"expected_marker": "alpha"},
            "rogue.md": {
                "expected_marker": "alpha",
                "extra": {"expected_event_class": "not-a-real-event-class"},
            },
        },
        taxonomy_classes=["alpha"],
    )
    rc, out, _ = _capture_main(
        [
            "--fixtures-dir", str(corpus),
            "--taxonomy-path", str(taxonomy_path),
            "--event-schema", str(event_schema_path),
        ]
    )
    assert rc == 1
    assert "dangling-event-class" in out
    assert "not-a-real-event-class" in out


def test_main_help_resolves() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


def test_main_with_no_flags_resolves_canonical_files() -> None:
    """main() with no argv resolves canonical examples/ + schemas/ via find_repo_root."""
    rc, out, _ = _capture_main([])
    assert rc == 0
    assert "examples/synthetic-stories" in out
    assert "schemas/marker-taxonomy.yaml" in out
    assert "schemas/orchestrator-event.yaml" in out


# ---------------------------------------------------------------------------
# Loud-fail / harness-level errors (AC-4, AC-6, Pattern 5)
# ---------------------------------------------------------------------------


def test_loud_fail_on_missing_fixtures_dir(tmp_path: pathlib.Path) -> None:
    taxonomy = tmp_path / "taxonomy.yaml"
    _write_taxonomy(taxonomy, ["alpha"])
    from loud_fail_harness._shared import find_repo_root

    event_schema = find_repo_root() / "schemas" / "orchestrator-event.yaml"
    rc, _, err = _capture_main(
        [
            "--fixtures-dir", str(tmp_path / "does-not-exist"),
            "--taxonomy-path", str(taxonomy),
            "--event-schema", str(event_schema),
        ]
    )
    assert rc == 2
    assert "harness-level error" in err
    assert "examples/synthetic-stories/" in err


def test_loud_fail_on_missing_taxonomy(tmp_path: pathlib.Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    from loud_fail_harness._shared import find_repo_root

    event_schema = find_repo_root() / "schemas" / "orchestrator-event.yaml"
    rc, _, err = _capture_main(
        [
            "--fixtures-dir", str(corpus),
            "--taxonomy-path", str(tmp_path / "missing-taxonomy.yaml"),
            "--event-schema", str(event_schema),
        ]
    )
    assert rc == 2
    assert "harness-level error" in err
    assert "marker-taxonomy" in err


def test_loud_fail_on_missing_event_schema(tmp_path: pathlib.Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    taxonomy = tmp_path / "taxonomy.yaml"
    _write_taxonomy(taxonomy, ["alpha"])
    rc, _, err = _capture_main(
        [
            "--fixtures-dir", str(corpus),
            "--taxonomy-path", str(taxonomy),
            "--event-schema", str(tmp_path / "missing-event-schema.yaml"),
        ]
    )
    assert rc == 2
    assert "harness-level error" in err
    assert "orchestrator-event schema unreadable" in err


def test_loud_fail_on_malformed_event_schema(tmp_path: pathlib.Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    taxonomy = tmp_path / "taxonomy.yaml"
    _write_taxonomy(taxonomy, ["alpha"])
    bad_schema = tmp_path / "bad-event-schema.yaml"
    # malformed JSON Schema: type must be a string or array of strings
    bad_schema.write_text("type: 99\n", encoding="utf-8")
    rc, _, err = _capture_main(
        [
            "--fixtures-dir", str(corpus),
            "--taxonomy-path", str(taxonomy),
            "--event-schema", str(bad_schema),
        ]
    )
    assert rc == 2
    assert "harness-level error" in err
    assert "orchestrator-event schema malformed" in err


def test_loud_fail_on_malformed_taxonomy(tmp_path: pathlib.Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    bad_taxonomy = tmp_path / "bad-taxonomy.yaml"
    bad_taxonomy.write_text("not_a_mapping_just_a_string\n", encoding="utf-8")
    from loud_fail_harness._shared import find_repo_root

    event_schema = find_repo_root() / "schemas" / "orchestrator-event.yaml"
    rc, _, err = _capture_main(
        [
            "--fixtures-dir", str(corpus),
            "--taxonomy-path", str(bad_taxonomy),
            "--event-schema", str(event_schema),
        ]
    )
    assert rc == 2
    assert "harness-level error" in err
    assert "marker-taxonomy" in err
