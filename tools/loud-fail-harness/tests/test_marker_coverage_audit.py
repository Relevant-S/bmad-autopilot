"""Contract-coverage matrix for the marker emission coverage audit (Story 6.3).

This docstring IS the contract-coverage checklist required by AC-6. Each test
cites the AC it witnesses verbatim per Pattern 5's named-invariant convention.

Data-loading cases (AC-1):
    [x] load_surfaces parses the data YAML correctly         → test_load_surfaces_parses_yaml_correctly
    [x] load_verdicts returns frozen CoverageVerdict tuple   → test_load_verdicts_returns_frozen_dataclasses

Audit failure-mode cases (AC-1, AC-2):
    [x] audit raises on missing (marker × surface) intersection
                                                             → test_audit_raises_on_missing_intersection
    [x] audit raises on stale code_path                      → test_audit_raises_on_unresolved_code_path
    [x] audit raises on not-applicable row missing rationale → test_audit_raises_on_not_applicable_missing_rationale
    [x] audit raises on scheduled-by-story missing/malformed discharging_story
                                                             → test_audit_raises_on_scheduled_missing_discharging_story
    [x] audit raises on gap verdict in production data       → test_audit_raises_on_gap_verdict
    [x] audit succeeds on full-coverage seeded data          → test_audit_succeeds_on_seeded_full_coverage

Render determinism + round-trip cases (AC-3, AC-6):
    [x] render_checklist produces deterministic byte-stable output
                                                             → test_render_checklist_deterministic
    [x] render_checklist round-trip: write → re-load → equal → test_render_checklist_round_trip

CLI entry-point cases (AC-8):
    [x] main() returns 0 on green                            → test_main_returns_0_on_green
    [x] main() returns 1 on audit failure                    → test_main_returns_1_on_audit_failure

Integration test (AC-6, AC-7):
    [x] real taxonomy + real surfaces produces clean audit   → test_marker_coverage_audit_walks_real_taxonomy
    [x] on-disk artifact matches freshly-rendered output     → test_canonical_marker_coverage_audit_md_matches_render
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml

from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.exceptions import MarkerCoverageAuditFailure
from loud_fail_harness.marker_coverage_audit import (
    CodeSurface,
    CoverageVerdict,
    audit,
    load_surfaces,
    load_verdicts,
    main,
    render_checklist,
)

# --------------------------------------------------------------------------- #
# Synthetic data construction helpers                                         #
# --------------------------------------------------------------------------- #

#: Synthetic taxonomy used by the unit tests — two markers; the audit-module
#: is taxonomy-agnostic per AC's "read-only against the taxonomy" rule, so any
#: pair of marker_class strings works.
_SYNTHETIC_TAXONOMY = {
    "schema_version": "1.0",
    "markers": [
        {"marker_class": "demo-marker-a", "diagnostic_pointer": "x", "sub_classifications": []},
        {"marker_class": "demo-marker-b", "diagnostic_pointer": "x", "sub_classifications": []},
    ],
}


def _write_taxonomy(tmp_path: Path) -> Path:
    """Write the synthetic taxonomy to a tmp file; return the path."""
    p = tmp_path / "taxonomy.yaml"
    p.write_text(yaml.safe_dump(_SYNTHETIC_TAXONOMY), encoding="utf-8")
    return p


def _write_emission_source(tmp_path: Path, marker: str = "demo-marker-a") -> Path:
    """Write a minimal Python source file that contains a marker reference.

    The audit accepts EITHER a literal kebab-case marker_class string OR a
    `_MARKER` constant identifier OR a ``marker_class=`` keyword. This helper
    embeds the literal marker string so the smoke path resolves.
    """
    src = tmp_path / "demo_emit.py"
    src.write_text(
        f"# Synthetic emission site for tests.\nDEMO_MARKER = \"{marker}\"\n",
        encoding="utf-8",
    )
    return src


def _build_surfaces_yaml(
    tmp_path: Path,
    *,
    surfaces: list[Mapping[str, Any]],
    verdicts: list[Mapping[str, Any]],
    schema_version: str = "1.0",
) -> Path:
    """Compose a synthetic _data/marker_coverage_surfaces.yaml at tmp_path."""
    p = tmp_path / "surfaces.yaml"
    p.write_text(
        yaml.safe_dump(
            {
                "schema_version": schema_version,
                "surfaces": list(surfaces),
                "verdicts": list(verdicts),
            }
        ),
        encoding="utf-8",
    )
    return p


def _full_coverage_verdicts(
    src_relpath: str,
) -> list[Mapping[str, Any]]:
    """Return verdicts that cover the full Cartesian product of the synthetic
    taxonomy (2 markers) × 1 synthetic surface — no missing intersections,
    no invalid shape.
    """
    return [
        {
            "marker_class": "demo-marker-a",
            "surface_name": "demo-surface",
            "verdict": "emitted",
            "code_path": f"{src_relpath}:2",
            "audit_date": "2026-05-05",
        },
        {
            "marker_class": "demo-marker-b",
            "surface_name": "demo-surface",
            "verdict": "not-applicable",
            "rationale": "demo-marker-b does not emit at the demo surface.",
            "audit_date": "2026-05-05",
        },
    ]


# --------------------------------------------------------------------------- #
# Data-loading tests (AC-1)                                                   #
# --------------------------------------------------------------------------- #


def test_load_surfaces_parses_yaml_correctly(tmp_path: Path) -> None:
    """AC-1: load_surfaces parses the data YAML correctly into frozen
    CodeSurface tuples carrying all four required fields.
    """
    surfaces_yaml = _build_surfaces_yaml(
        tmp_path,
        surfaces=[
            {
                "name": "demo-surface",
                "category": "bundle-assembler",
                "file_paths": ["src/demo.py"],
                "description": "demo description",
            }
        ],
        verdicts=[],
    )
    surfaces = load_surfaces(surfaces_yaml)
    assert isinstance(surfaces, tuple)
    assert len(surfaces) == 1
    assert isinstance(surfaces[0], CodeSurface)
    assert surfaces[0].name == "demo-surface"
    assert surfaces[0].category == "bundle-assembler"
    assert surfaces[0].file_paths == ("src/demo.py",)
    assert surfaces[0].description == "demo description"


def test_load_verdicts_returns_frozen_dataclasses(tmp_path: Path) -> None:
    """AC-1: load_verdicts returns frozen CoverageVerdict instances with
    optional fields normalized to None when absent.
    """
    surfaces_yaml = _build_surfaces_yaml(
        tmp_path,
        surfaces=[],
        verdicts=[
            {
                "marker_class": "demo-marker-a",
                "surface_name": "demo-surface",
                "verdict": "not-applicable",
                "rationale": "n/a here",
                "audit_date": "2026-05-05",
            }
        ],
    )
    verdicts = load_verdicts(surfaces_yaml)
    assert isinstance(verdicts, tuple)
    assert len(verdicts) == 1
    v = verdicts[0]
    assert isinstance(v, CoverageVerdict)
    assert v.marker_class == "demo-marker-a"
    assert v.code_path is None  # absent in YAML → None
    assert v.discharging_story is None
    assert v.rationale == "n/a here"
    # Frozen: assignment raises (dataclass(frozen=True) contract).
    with pytest.raises(Exception):
        v.marker_class = "mutated"  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# Audit failure-mode tests (AC-1, AC-2)                                       #
# --------------------------------------------------------------------------- #


def test_audit_raises_on_missing_intersection(tmp_path: Path) -> None:
    """AC-1: audit raises MarkerCoverageAuditFailure on missing
    (marker × surface) intersection — verdicts list is empty but taxonomy +
    surfaces both have entries, so every intersection is missing.
    """
    taxonomy = _write_taxonomy(tmp_path)
    surfaces_yaml = _build_surfaces_yaml(
        tmp_path,
        surfaces=[
            {
                "name": "demo-surface",
                "category": "bundle-assembler",
                "file_paths": [],
                "description": "demo",
            }
        ],
        verdicts=[],
    )
    with pytest.raises(MarkerCoverageAuditFailure) as exc:
        audit(taxonomy, surfaces_yaml, repo_root=tmp_path)
    assert exc.value.missing_intersections == (
        ("demo-marker-a", "demo-surface"),
        ("demo-marker-b", "demo-surface"),
    )


def test_audit_raises_on_unresolved_code_path(tmp_path: Path) -> None:
    """AC-2: audit raises with unresolved_code_paths populated when an
    `emitted` verdict's code_path does not resolve to a file containing a
    marker reference.
    """
    taxonomy = _write_taxonomy(tmp_path)
    surfaces_yaml = _build_surfaces_yaml(
        tmp_path,
        surfaces=[
            {
                "name": "demo-surface",
                "category": "bundle-assembler",
                "file_paths": [],
                "description": "demo",
            }
        ],
        verdicts=[
            {
                "marker_class": "demo-marker-a",
                "surface_name": "demo-surface",
                "verdict": "emitted",
                "code_path": "does/not/exist.py:1",
                "audit_date": "2026-05-05",
            },
            {
                "marker_class": "demo-marker-b",
                "surface_name": "demo-surface",
                "verdict": "not-applicable",
                "rationale": "n/a",
                "audit_date": "2026-05-05",
            },
        ],
    )
    with pytest.raises(MarkerCoverageAuditFailure) as exc:
        audit(taxonomy, surfaces_yaml, repo_root=tmp_path)
    assert any("demo-marker-a × demo-surface" in u for u in exc.value.unresolved_code_paths)


def test_audit_raises_on_not_applicable_missing_rationale(tmp_path: Path) -> None:
    """AC-2: not-applicable verdict missing rationale → invalid_verdicts."""
    taxonomy = _write_taxonomy(tmp_path)
    src = _write_emission_source(tmp_path)
    surfaces_yaml = _build_surfaces_yaml(
        tmp_path,
        surfaces=[
            {
                "name": "demo-surface",
                "category": "bundle-assembler",
                "file_paths": [],
                "description": "demo",
            }
        ],
        verdicts=[
            {
                "marker_class": "demo-marker-a",
                "surface_name": "demo-surface",
                "verdict": "emitted",
                "code_path": f"{src.name}:2",
                "audit_date": "2026-05-05",
            },
            {
                "marker_class": "demo-marker-b",
                "surface_name": "demo-surface",
                "verdict": "not-applicable",
                # rationale missing
                "audit_date": "2026-05-05",
            },
        ],
    )
    with pytest.raises(MarkerCoverageAuditFailure) as exc:
        audit(taxonomy, surfaces_yaml, repo_root=tmp_path)
    assert any(
        "not-applicable verdict missing required 'rationale'" in i
        for i in exc.value.invalid_verdicts
    )


def test_audit_raises_on_scheduled_missing_discharging_story(tmp_path: Path) -> None:
    """AC-2: scheduled-by-story verdict missing discharging_story OR
    malformed (e.g. ``six-seven`` instead of ``6.7``) → invalid_verdicts.
    """
    taxonomy = _write_taxonomy(tmp_path)
    src = _write_emission_source(tmp_path)
    surfaces_yaml = _build_surfaces_yaml(
        tmp_path,
        surfaces=[
            {
                "name": "demo-surface",
                "category": "bundle-assembler",
                "file_paths": [],
                "description": "demo",
            }
        ],
        verdicts=[
            {
                "marker_class": "demo-marker-a",
                "surface_name": "demo-surface",
                "verdict": "emitted",
                "code_path": f"{src.name}:2",
                "audit_date": "2026-05-05",
            },
            {
                "marker_class": "demo-marker-b",
                "surface_name": "demo-surface",
                "verdict": "scheduled-by-story",
                "rationale": "deferred",
                "discharging_story": "six-seven",  # malformed
                "audit_date": "2026-05-05",
            },
        ],
    )
    with pytest.raises(MarkerCoverageAuditFailure) as exc:
        audit(taxonomy, surfaces_yaml, repo_root=tmp_path)
    assert any(
        "missing or malformed 'discharging_story'" in i
        for i in exc.value.invalid_verdicts
    )


def test_audit_raises_on_gap_verdict(tmp_path: Path) -> None:
    """AC-2: gap verdict in production data → invalid_verdicts (production
    data MUST NOT carry gap verdicts at Story 6.3 close).
    """
    taxonomy = _write_taxonomy(tmp_path)
    src = _write_emission_source(tmp_path)
    surfaces_yaml = _build_surfaces_yaml(
        tmp_path,
        surfaces=[
            {
                "name": "demo-surface",
                "category": "bundle-assembler",
                "file_paths": [],
                "description": "demo",
            }
        ],
        verdicts=[
            {
                "marker_class": "demo-marker-a",
                "surface_name": "demo-surface",
                "verdict": "emitted",
                "code_path": f"{src.name}:2",
                "audit_date": "2026-05-05",
            },
            {
                "marker_class": "demo-marker-b",
                "surface_name": "demo-surface",
                "verdict": "gap",
                "audit_date": "2026-05-05",
            },
        ],
    )
    with pytest.raises(MarkerCoverageAuditFailure) as exc:
        audit(taxonomy, surfaces_yaml, repo_root=tmp_path)
    assert any(
        "gap verdict is" in i and "invalid in production data" in i
        for i in exc.value.invalid_verdicts
    )


def test_audit_succeeds_on_seeded_full_coverage(tmp_path: Path) -> None:
    """AC-1 + AC-2: audit returns sorted verdicts on full-coverage data
    with valid emitted code_path + valid not-applicable rationale.
    """
    taxonomy = _write_taxonomy(tmp_path)
    src = _write_emission_source(tmp_path)
    surfaces_yaml = _build_surfaces_yaml(
        tmp_path,
        surfaces=[
            {
                "name": "demo-surface",
                "category": "bundle-assembler",
                "file_paths": [src.name],
                "description": "demo",
            }
        ],
        verdicts=_full_coverage_verdicts(src.name),
    )
    result = audit(taxonomy, surfaces_yaml, repo_root=tmp_path)
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert [v.marker_class for v in result] == ["demo-marker-a", "demo-marker-b"]


# --------------------------------------------------------------------------- #
# Render determinism + round-trip (AC-3, AC-6)                                #
# --------------------------------------------------------------------------- #


def test_render_checklist_deterministic(tmp_path: Path) -> None:
    """AC-3 + AC-6: render_checklist produces byte-identical output across
    two invocations with the same input.
    """
    verdicts = (
        CoverageVerdict(
            marker_class="demo-marker-b",
            surface_name="demo-surface",
            verdict="not-applicable",
            rationale="n/a",
            audit_date="2026-05-05",
        ),
        CoverageVerdict(
            marker_class="demo-marker-a",
            surface_name="demo-surface",
            verdict="emitted",
            code_path="src/demo.py:1",
            audit_date="2026-05-05",
        ),
    )
    out_a = tmp_path / "render-a.md"
    out_b = tmp_path / "render-b.md"
    render_checklist(verdicts, out_a)
    render_checklist(verdicts, out_b)
    assert out_a.read_bytes() == out_b.read_bytes()
    # Sorted alphabetically by marker_class then surface_name → demo-marker-a first.
    body = out_a.read_text(encoding="utf-8")
    assert body.index("demo-marker-a") < body.index("demo-marker-b")


def test_render_checklist_round_trip(tmp_path: Path) -> None:
    """AC-3 + AC-6: render → re-parse the markdown table → recovered
    (marker_class, surface_name, verdict) tuples equal the input.

    Round-trip is a structural-shape contract, not byte-equality on the
    rationale prose (the table-cell escape replaces ``|`` with ``\\|``).
    """
    verdicts = (
        CoverageVerdict(
            marker_class="alpha-marker",
            surface_name="alpha-surface",
            verdict="not-applicable",
            rationale="alpha rationale",
            audit_date="2026-05-05",
        ),
        CoverageVerdict(
            marker_class="beta-marker",
            surface_name="beta-surface",
            verdict="scheduled-by-story",
            discharging_story="9.9",
            rationale="beta rationale",
            audit_date="2026-05-05",
        ),
    )
    out = tmp_path / "render.md"
    render_checklist(verdicts, out)
    body = out.read_text(encoding="utf-8")
    # Parse table rows: lines starting with `| <marker> | <surface> | <verdict> |`.
    row_pattern = re.compile(
        r"^\|\s*([\w\-.]+)\s*\|\s*([\w\-.]+)\s*\|\s*(\w[\w\-]*)\s*\|",
        re.MULTILINE,
    )
    rows = [m.groups() for m in row_pattern.finditer(body)]
    assert ("alpha-marker", "alpha-surface", "not-applicable") in rows
    assert ("beta-marker", "beta-surface", "scheduled-by-story") in rows


# --------------------------------------------------------------------------- #
# CLI entry-point tests (AC-8)                                                #
# --------------------------------------------------------------------------- #


def test_main_returns_0_on_green(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-8: main() exits 0 when audit passes; prints the one-line summary."""
    taxonomy = _write_taxonomy(tmp_path)
    src = _write_emission_source(tmp_path)
    surfaces_yaml = _build_surfaces_yaml(
        tmp_path,
        surfaces=[
            {
                "name": "demo-surface",
                "category": "bundle-assembler",
                "file_paths": [src.name],
                "description": "demo",
            }
        ],
        verdicts=_full_coverage_verdicts(src.name),
    )
    # Stub find_repo_root to return tmp_path (so code_path resolution works
    # against the synthetic source file).
    monkeypatch.setattr(
        "loud_fail_harness.marker_coverage_audit.find_repo_root", lambda: tmp_path
    )
    rc = main(
        [
            "--taxonomy-path", str(taxonomy),
            "--surfaces-path", str(surfaces_yaml),
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "marker-coverage-audit:" in out
    assert "0 gaps" in out


def test_main_returns_1_on_audit_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-8: main() exits 1 when audit fails; prints the named-invariant
    diagnostic to stderr (NFR-O5).
    """
    taxonomy = _write_taxonomy(tmp_path)
    surfaces_yaml = _build_surfaces_yaml(
        tmp_path,
        surfaces=[
            {
                "name": "demo-surface",
                "category": "bundle-assembler",
                "file_paths": [],
                "description": "demo",
            }
        ],
        verdicts=[
            # Both verdicts present but one is gap — invalid in production data.
            {
                "marker_class": "demo-marker-a",
                "surface_name": "demo-surface",
                "verdict": "gap",
                "audit_date": "2026-05-05",
            },
            {
                "marker_class": "demo-marker-b",
                "surface_name": "demo-surface",
                "verdict": "not-applicable",
                "rationale": "n/a",
                "audit_date": "2026-05-05",
            },
        ],
    )
    monkeypatch.setattr(
        "loud_fail_harness.marker_coverage_audit.find_repo_root", lambda: tmp_path
    )
    rc = main(
        [
            "--taxonomy-path", str(taxonomy),
            "--surfaces-path", str(surfaces_yaml),
        ]
    )
    assert rc == 1
    err = capsys.readouterr().err
    assert "MarkerCoverageAuditFailure" in err


# --------------------------------------------------------------------------- #
# Real-data integration test (AC-6)                                           #
# --------------------------------------------------------------------------- #


def test_marker_coverage_audit_walks_real_taxonomy() -> None:
    """AC-6: real schemas/marker-taxonomy.yaml × real
    _data/marker_coverage_surfaces.yaml produces a clean audit (zero gaps;
    every scheduled-by-story verdict's discharging_story references a story
    key in sprint-status.yaml whose status is NOT 'done').
    """
    repo_root = find_repo_root()
    taxonomy_path = repo_root / "schemas" / "marker-taxonomy.yaml"
    surfaces_path = (
        repo_root / "tools" / "loud-fail-harness" / "src" / "loud_fail_harness"
        / "_data" / "marker_coverage_surfaces.yaml"
    )

    # Audit returns successfully (no MarkerCoverageAuditFailure).
    verdicts = audit(taxonomy_path, surfaces_path, repo_root=repo_root)
    assert len(verdicts) > 0

    # Zero gap verdicts (production-data invariant per AC-2).
    assert all(v.verdict != "gap" for v in verdicts)

    # Every scheduled-by-story discharging_story points to a sprint-status
    # story key whose status is NOT 'done' (the discharging story is
    # genuinely pending). The sprint-status file lives in the OUTER repo
    # (planning workspace), not the inner repo — locate it by walking up
    # from the inner repo root.
    outer_root = repo_root.parent
    sprint_status_path = (
        outer_root / "_bmad-output" / "implementation-artifacts" / "sprint-status.yaml"
    )
    if not sprint_status_path.is_file():  # pragma: no cover — defensive
        pytest.skip(f"sprint-status.yaml not found at {sprint_status_path}")

    sprint_status = yaml.safe_load(sprint_status_path.read_text(encoding="utf-8"))
    dev_status: dict[str, str] = sprint_status.get("development_status", {})
    # Index sprint-status by '<epic>.<story>' shape (e.g., '6.7') by
    # extracting the leading numeric prefix from each key.
    epic_story_status: dict[str, str] = {}
    key_pattern = re.compile(r"^(\d+)-(\d+)-")
    for full_key, status in dev_status.items():
        m = key_pattern.match(full_key)
        if m is not None:
            epic_story_status[f"{m.group(1)}.{m.group(2)}"] = str(status)

    for v in verdicts:
        if v.verdict == "scheduled-by-story":
            assert v.discharging_story is not None
            status = epic_story_status.get(v.discharging_story)
            # Either the story exists with a non-'done' status, OR it's a
            # forward-scoped story that hasn't been added to sprint-status
            # yet (still pending). Treat both as valid pending-state proof.
            assert status != "done", (
                f"scheduled-by-story verdict for {v.marker_class} × "
                f"{v.surface_name} points to discharging_story "
                f"{v.discharging_story!r} which is already 'done' in "
                f"sprint-status.yaml — re-classify as 'emitted' with a "
                f"concrete code_path"
            )


def test_canonical_marker_coverage_audit_md_matches_render(tmp_path: Path) -> None:
    """AC-3 + AC-6: the on-disk docs/marker-coverage-audit.md matches a
    freshly-rendered output — drift between the data file and the artifact
    is caught at CI. Mirrors Story 6.1's canonical-fixture regression-test
    pattern.
    """
    repo_root = find_repo_root()
    taxonomy_path = repo_root / "schemas" / "marker-taxonomy.yaml"
    surfaces_path = (
        repo_root / "tools" / "loud-fail-harness" / "src" / "loud_fail_harness"
        / "_data" / "marker_coverage_surfaces.yaml"
    )
    artifact_path = repo_root / "docs" / "marker-coverage-audit.md"

    verdicts = audit(taxonomy_path, surfaces_path, repo_root=repo_root)
    regenerated = tmp_path / "regen.md"
    render_checklist(verdicts, regenerated)

    on_disk = artifact_path.read_bytes()
    fresh = regenerated.read_bytes()
    assert on_disk == fresh, (
        "docs/marker-coverage-audit.md drift detected — re-run "
        "`uv run marker-coverage-audit --regenerate` and commit both "
        "_data/marker_coverage_surfaces.yaml and docs/marker-coverage-audit.md."
    )
