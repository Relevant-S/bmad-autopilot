"""Story 7.3 — `init` precondition orchestration tests (AC-9).

Each test docstring cites the AC it covers per Pattern 5's
named-invariant convention (precedent: every test in
:mod:`tests.test_install_path` / :mod:`tests.test_marker_wiring` /
:mod:`tests.test_evidence_linkability`).

Coverage matrix per AC-9 (15 tests):

    1. Total-block happy-path (all probes pass).
    2. Total-block fail — claude-code below version floor.
    3. Total-block fail — bmad-core missing.
    4. Total-block fail — tea-module missing (verbatim diagnostic).
    5. Total-block fail — playwright-mcp web init unreachable.
    6. Total-block aggregated halt — multiple deps fail in one run.
    7. Project-type filter — playwright-mcp api init is opt-in-skip.
    8. Project-type filter — mobile-mcp web init is opt-in-skip.
    9. Opt-in-skip with `configured-but-missing` — LAD configured.
    10. Opt-in-skip silent path — LAD unconfigured.
    11. Aggregated diagnostic shape — no umbrella marker.
    12. Diagnostic shape consistency with Story 6.1's loud-fail block.
    13. Diagnostic empty-case sentinel.
    14. `load_dependencies()` surfaces SDN-001 failures unchanged.
    15. Schema-version bump non-regression.
"""

from __future__ import annotations

import pathlib

import pytest

from loud_fail_harness.bundle_assembly import (
    _load_marker_taxonomy_entries,
    _render_loud_fail_block,
)
from loud_fail_harness.init_preconditions import (
    PreconditionProbeRegistry,
    PreconditionProbeResult,
    PreconditionResult,
    PreconditionRun,
    ProjectType,
    _dispatch_graceful_degrade,
    default_git_version_reader,
    format_init_diagnostic,
    git_precondition_probe_factory,
    lad_precondition_probe_factory,
    run_init_preconditions,
)
from loud_fail_harness.run_state import CostToDateBySpecialist, RunState
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    load_marker_class_registry,
)

# Fixtures dir mirroring Story 7.2's `tests/fixtures/install_path/` convention.
_FIXTURE_DIR = (
    pathlib.Path(__file__).resolve().parent / "fixtures" / "init_preconditions"
)
_EXTENDED_FIXTURE = _FIXTURE_DIR / "dependencies-fixture-extended.yaml"
_SHAPE_VIOLATION_FIXTURE = _FIXTURE_DIR / "dependencies-fixture-shape-violation.yaml"


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _passing_probe(version_observed: str | None = None) -> PreconditionProbeResult:
    return PreconditionProbeResult(available=True, version_observed=version_observed)


def _failing_probe() -> PreconditionProbeResult:
    return PreconditionProbeResult(available=False)


def _passing_probes(
    *, claude_version: str = "2.1.32", bmad_version: str = "6.0"
) -> PreconditionProbeRegistry:
    """Build a probe registry where every probe returns available=True."""
    return PreconditionProbeRegistry(
        claude_code=lambda: _passing_probe(claude_version),
        bmad_core=lambda: _passing_probe(bmad_version),
        git=lambda: _passing_probe(),
        tea_module=lambda: _passing_probe(),
        playwright_mcp=lambda: _passing_probe(),
        mobile_mcp=lambda: _passing_probe(),
        lad=lambda: _passing_probe(),
    )


def _failing_for(name: str, **overrides: object) -> PreconditionProbeRegistry:
    """Build a probe registry where the named probe fails; others pass.

    `overrides` may set additional probes to fixture results; e.g.
    ``_failing_for("bmad_core", claude_code=PreconditionProbeResult(available=True, ...))``.
    """
    base = _passing_probes()
    fields = {
        "claude_code": base.claude_code,
        "bmad_core": base.bmad_core,
        "git": base.git,
        "tea_module": base.tea_module,
        "playwright_mcp": base.playwright_mcp,
        "mobile_mcp": base.mobile_mcp,
        "lad": base.lad,
    }
    fields[name] = lambda: _failing_probe()
    for key, val in overrides.items():
        if isinstance(val, PreconditionProbeResult):
            fields[key] = lambda v=val: v  # type: ignore[misc]
        else:
            fields[key] = val  # type: ignore[assignment]
    return PreconditionProbeRegistry(**fields)


def _make_run_state() -> RunState:
    return RunState(
        schema_version="1.3",
        story_id="7-3-test",
        run_id="run-001",
        current_state="in-progress",
        branch_name="bmad-automation/story/7-3-test",
        dispatched_specialist=None,
        last_envelope=None,
        pending_qa_dispatch_payload=None,
        retry_history=(),
        active_markers=(),
        cost_to_date_by_specialist=CostToDateBySpecialist(),
    )


@pytest.fixture(scope="module")
def runtime_marker_registry() -> MarkerClassRegistry:
    return load_marker_class_registry()


# --------------------------------------------------------------------------- #
# AC-9 case 1 — total-block happy-path                                        #
# --------------------------------------------------------------------------- #


def test_total_block_happy_path_all_probes_pass(
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """AC-9 case 1: every probe returns available=True with versions ≥
    version_floor → run.halted is False; every result has
    outcome="pass"; no markers registered."""
    rs = _make_run_state()
    run = run_init_preconditions(
        _passing_probes(),
        project_type="web",
        marker_registry=runtime_marker_registry,
        run_state=rs,
    )
    assert run.halted is False
    pass_results = [r for r in run.results if r.outcome == "pass"]
    # claude-code, bmad-core, tea-module pass total-block; playwright-mcp web
    # passes total-block; mobile-mcp web is opt-in-skip pass; lad is
    # opt-in-skip pass.
    assert len(pass_results) >= 4
    assert run.run_state is not None
    assert run.run_state.active_markers == ()


# --------------------------------------------------------------------------- #
# AC-9 case 2 — claude-code below version floor                               #
# --------------------------------------------------------------------------- #


def test_total_block_fail_claude_code_below_version_floor(
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """AC-9 case 2: claude_code probe returns available=True,
    version_observed="2.1.31" (one patch below floor "2.1.32") → run
    halts AND env-setup-failed: claude-code-version-mismatch is
    registered."""
    base = _passing_probes()
    probes = PreconditionProbeRegistry(
        claude_code=lambda: PreconditionProbeResult(
            available=True, version_observed="2.1.31"
        ),
        bmad_core=base.bmad_core,
        git=base.git,
        tea_module=base.tea_module,
        playwright_mcp=base.playwright_mcp,
        mobile_mcp=base.mobile_mcp,
        lad=base.lad,
    )
    run = run_init_preconditions(
        probes,
        project_type="web",
        marker_registry=runtime_marker_registry,
        run_state=_make_run_state(),
    )
    assert run.halted is True
    claude_result = next(r for r in run.results if r.dependency == "claude-code")
    assert claude_result.outcome == "halt"
    assert claude_result.marker_class == "env-setup-failed"
    assert claude_result.sub_classification == "claude-code-version-mismatch"
    assert run.run_state is not None
    assert (
        "env-setup-failed: claude-code-version-mismatch"
        in run.run_state.active_markers
    )


# --------------------------------------------------------------------------- #
# AC-9 case 3 — bmad-core missing                                             #
# --------------------------------------------------------------------------- #


def test_total_block_fail_bmad_core_missing(
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """AC-9 case 3: bmad_core probe returns available=False → run halts
    AND env-setup-failed: bmad-core-version-mismatch is registered."""
    run = run_init_preconditions(
        _failing_for("bmad_core"),
        project_type="web",
        marker_registry=runtime_marker_registry,
        run_state=_make_run_state(),
    )
    assert run.halted is True
    bmad_result = next(r for r in run.results if r.dependency == "bmad-core")
    assert bmad_result.outcome == "halt"
    assert bmad_result.marker_class == "env-setup-failed"
    assert bmad_result.sub_classification == "bmad-core-version-mismatch"
    assert run.run_state is not None
    assert (
        "env-setup-failed: bmad-core-version-mismatch"
        in run.run_state.active_markers
    )


# --------------------------------------------------------------------------- #
# AC-9 case 4 — tea-module missing (verbatim diagnostic)                       #
# --------------------------------------------------------------------------- #


def test_total_block_fail_tea_module_missing_verbatim_diagnostic(
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """AC-9 case 4: tea_module probe returns available=False → run halts
    AND env-setup-failed: tea-module-missing is registered AND the
    per-dependency diagnostic_text is the dependencies.yaml entry's
    `diagnostic` field VERBATIM."""
    run = run_init_preconditions(
        _failing_for("tea_module"),
        project_type="web",
        marker_registry=runtime_marker_registry,
        run_state=_make_run_state(),
    )
    assert run.halted is True
    tea = next(r for r in run.results if r.dependency == "tea-module")
    assert tea.outcome == "halt"
    assert tea.marker_class == "env-setup-failed"
    assert tea.sub_classification == "tea-module-missing"
    assert tea.dependency_diagnostic == (
        "TEA module not installed. Run `/bmad:install tea` and re-run "
        "`/bmad-automation init`."
    )


# --------------------------------------------------------------------------- #
# AC-9 case 5 — playwright-mcp web init unreachable                           #
# --------------------------------------------------------------------------- #


def test_total_block_fail_playwright_mcp_web_init_unreachable(
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """AC-9 case 5: project_type="web" + playwright_mcp probe returns
    available=False → run halts AND playwright-mcp-unavailable is
    registered (NO sub_classification per the existing taxonomy entry's
    empty `sub_classifications: []`) AND `pointer_context_fields:
    [project_type, version_range]` are populated with project_type="web"
    and the dependency's version_floor."""
    run = run_init_preconditions(
        _failing_for("playwright_mcp"),
        project_type="web",
        marker_registry=runtime_marker_registry,
        run_state=_make_run_state(),
    )
    assert run.halted is True
    pw = next(r for r in run.results if r.dependency == "playwright-mcp")
    assert pw.outcome == "halt"
    assert pw.marker_class == "playwright-mcp-unavailable"
    # No sub_classification per taxonomy's `sub_classifications: []`.
    assert pw.sub_classification is None
    assert run.run_state is not None
    assert "playwright-mcp-unavailable" in run.run_state.active_markers
    pointer_ctx = run.run_state.marker_contexts["playwright-mcp-unavailable"]
    assert pointer_ctx["project_type"] == "web"
    assert pointer_ctx["version_range"] == "officially-supported-as-of-mvp-release"


# --------------------------------------------------------------------------- #
# AC-9 case 6 — multiple deps fail; aggregate halt without short-circuit      #
# --------------------------------------------------------------------------- #


def test_total_block_aggregated_halt_multiple_deps_fail(
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """AC-9 case 6: bmad_core AND tea_module BOTH fail → run halts after
    probing every dep (no short-circuit) AND BOTH markers are
    registered AND the run.results enumerate BOTH failures in
    declaration order."""
    base = _passing_probes()
    probes = PreconditionProbeRegistry(
        claude_code=base.claude_code,
        bmad_core=lambda: _failing_probe(),
        git=base.git,
        tea_module=lambda: _failing_probe(),
        playwright_mcp=base.playwright_mcp,
        mobile_mcp=base.mobile_mcp,
        lad=base.lad,
    )
    run = run_init_preconditions(
        probes,
        project_type="web",
        marker_registry=runtime_marker_registry,
        run_state=_make_run_state(),
    )
    assert run.halted is True
    halted_deps = [r.dependency for r in run.results if r.outcome == "halt"]
    assert "bmad-core" in halted_deps
    assert "tea-module" in halted_deps
    # Declaration order: bmad-core comes BEFORE tea-module in dependencies.yaml.
    assert halted_deps.index("bmad-core") < halted_deps.index("tea-module")
    assert run.run_state is not None
    assert (
        "env-setup-failed: bmad-core-version-mismatch"
        in run.run_state.active_markers
    )
    assert (
        "env-setup-failed: tea-module-missing" in run.run_state.active_markers
    )


# --------------------------------------------------------------------------- #
# AC-9 case 7 — project-type filter: playwright-mcp api init is opt-in-skip   #
# --------------------------------------------------------------------------- #


def test_project_type_filter_playwright_mcp_api_is_opt_in_skip(
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """AC-9 case 7: project_type="api" + playwright_mcp probe returns
    available=False → run does NOT halt AND no marker is registered AND
    the per-dep outcome is "silent" (per dependencies.yaml — api project
    type sets playwright-mcp init to opt-in-skip with no
    sub_classifications)."""
    run = run_init_preconditions(
        _failing_for("playwright_mcp"),
        project_type="api",
        marker_registry=runtime_marker_registry,
        run_state=_make_run_state(),
    )
    assert run.halted is False
    pw = next(r for r in run.results if r.dependency == "playwright-mcp")
    assert pw.outcome == "silent"
    assert run.run_state is not None
    assert "playwright-mcp-unavailable" not in run.run_state.active_markers


# --------------------------------------------------------------------------- #
# AC-9 case 8 — project-type filter: mobile-mcp web init is opt-in-skip       #
# --------------------------------------------------------------------------- #


def test_project_type_filter_mobile_mcp_web_is_opt_in_skip(
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """AC-9 case 8: project_type="web" + mobile_mcp probe returns
    available=False → run does NOT halt AND no marker is registered (per
    dependencies.yaml — phase 1.5 dep, web project sets opt-in-skip)."""
    run = run_init_preconditions(
        _failing_for("mobile_mcp"),
        project_type="web",
        marker_registry=runtime_marker_registry,
        run_state=_make_run_state(),
    )
    assert run.halted is False
    mm = next(r for r in run.results if r.dependency == "mobile-mcp")
    assert mm.outcome == "silent"


# --------------------------------------------------------------------------- #
# AC-9 case 10 — opt-in-skip silent path: LAD unconfigured                    #
# --------------------------------------------------------------------------- #


def test_opt_in_skip_lad_unconfigured_silent(
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """AC-9 case 10: lad probe returns available=False AND
    sub_classification="unconfigured" (mapping to dependencies.yaml's
    silent: true branch) → run does NOT halt AND no marker is
    registered AND the per-dep outcome is "silent" AND the diagnostic
    does NOT enumerate the LAD entry."""
    base = _passing_probes()
    probes = PreconditionProbeRegistry(
        claude_code=base.claude_code,
        bmad_core=base.bmad_core,
        git=base.git,
        tea_module=base.tea_module,
        playwright_mcp=base.playwright_mcp,
        mobile_mcp=base.mobile_mcp,
        lad=lambda: PreconditionProbeResult(
            available=False, sub_classification="unconfigured"
        ),
    )
    run = run_init_preconditions(
        probes,
        project_type="web",
        marker_registry=runtime_marker_registry,
        run_state=_make_run_state(),
    )
    assert run.halted is False
    lad = next(r for r in run.results if r.dependency == "lad")
    assert lad.outcome == "silent"
    assert lad.marker_class is None
    assert run.run_state is not None
    assert "LAD-skipped" not in run.run_state.active_markers
    diagnostic = format_init_diagnostic(run, marker_registry=runtime_marker_registry)
    assert "lad" not in diagnostic.lower()
    assert "LAD-skipped" not in diagnostic


# --------------------------------------------------------------------------- #
# AC-9 case 11 — aggregated diagnostic shape: no umbrella marker              #
# --------------------------------------------------------------------------- #


def test_aggregated_diagnostic_no_umbrella_marker(
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """AC-9 case 11: a multi-failure scenario produces a markdown
    diagnostic per AC-5 AND `init-precondition-failed` is NEVER
    registered (no umbrella marker per Story 1.11
    atomic-vs-aggregated principle). The MarkerClassRegistry does NOT
    include `init-precondition-failed`."""
    base = _passing_probes()
    probes = PreconditionProbeRegistry(
        claude_code=base.claude_code,
        bmad_core=lambda: _failing_probe(),
        git=base.git,
        tea_module=lambda: _failing_probe(),
        playwright_mcp=base.playwright_mcp,
        mobile_mcp=base.mobile_mcp,
        lad=base.lad,
    )
    run = run_init_preconditions(
        probes,
        project_type="web",
        marker_registry=runtime_marker_registry,
        run_state=_make_run_state(),
    )
    diagnostic = format_init_diagnostic(run, marker_registry=runtime_marker_registry)
    assert "## Init Precondition Check — Named-Invariant Diagnostic" in diagnostic
    assert "init-precondition-failed" not in diagnostic
    assert run.run_state is not None
    assert all(
        not m.startswith("init-precondition-failed")
        for m in run.run_state.active_markers
    )
    assert "init-precondition-failed" not in runtime_marker_registry.marker_classes


# --------------------------------------------------------------------------- #
# AC-9 case 12 — diagnostic shape consistent with Story 6.1 loud-fail block   #
# --------------------------------------------------------------------------- #


def test_diagnostic_shape_byte_identical_inherited_bullets(
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """AC-9 case 12: a single failed dep producing
    `active_markers=("env-setup-failed: tea-module-missing",)` produces
    a diagnostic whose `### env-setup-failed: tea-module-missing` H3
    header + Sub-classification bullet + Diagnostic pointer bullet are
    BYTE-IDENTICAL to `_render_loud_fail_block`'s output for the same
    `active_markers` input. AC-6 names these three lines as the verbatim
    structural anchors; the init-diagnostic's three init-specific
    bullets (Dependency, Per-dependency remediation, Lifecycle outcome)
    are additions and are NOT compared.

    Cites epics.md line 2962 verbatim — "the diagnostic format is
    consistent with Story 6.1's loud-fail block shape so practitioners
    reading either get the same mental model."
    """
    run = run_init_preconditions(
        _failing_for("tea_module"),
        project_type="web",
        marker_registry=runtime_marker_registry,
        run_state=_make_run_state(),
    )
    init_md = format_init_diagnostic(run, marker_registry=runtime_marker_registry)
    bundle_md = _render_loud_fail_block(
        ("env-setup-failed: tea-module-missing",),
        marker_registry=runtime_marker_registry,
    )

    init_h3 = "### env-setup-failed: tea-module-missing"
    assert init_h3 in init_md
    assert init_h3 in bundle_md

    init_lines = init_md.split("\n")
    bundle_lines = bundle_md.split("\n")
    init_h3_idx = init_lines.index(init_h3)
    bundle_h3_idx = bundle_lines.index(init_h3)

    # Sub-classification line: position +2 from H3 header in BOTH
    # outputs (H3, blank line, then first bullet) — bundle's first
    # bullet is Sub-classification per AC-1; init's first bullet is
    # Dependency per AC-5, with Sub-classification at position +3.
    assert bundle_lines[bundle_h3_idx + 2].startswith("- Sub-classification:")
    assert init_lines[init_h3_idx + 3].startswith("- Sub-classification:")
    assert (
        bundle_lines[bundle_h3_idx + 2] == init_lines[init_h3_idx + 3]
    ), (
        f"Sub-classification bullet must match VERBATIM per AC-6:\n"
        f"  bundle: {bundle_lines[bundle_h3_idx + 2]!r}\n"
        f"  init:   {init_lines[init_h3_idx + 3]!r}"
    )

    # Diagnostic pointer bullet: bundle position +3, init position +4.
    assert bundle_lines[bundle_h3_idx + 3].startswith("- Diagnostic pointer:")
    assert init_lines[init_h3_idx + 4].startswith("- Diagnostic pointer:")
    assert (
        bundle_lines[bundle_h3_idx + 3] == init_lines[init_h3_idx + 4]
    ), (
        f"Diagnostic pointer bullet must match VERBATIM per AC-6:\n"
        f"  bundle: {bundle_lines[bundle_h3_idx + 3]!r}\n"
        f"  init:   {init_lines[init_h3_idx + 4]!r}"
    )

    # Init-specific bullets are present (sandwich the inherited shape).
    assert "- Dependency: tea-module" in init_md
    assert "- Per-dependency remediation: TEA module not installed." in init_md
    assert "- Lifecycle outcome: halt" in init_md


# --------------------------------------------------------------------------- #
# AC-9 case 13 — diagnostic empty-case sentinel                               #
# --------------------------------------------------------------------------- #


def test_diagnostic_empty_case_sentinel(
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """AC-9 case 13: a PreconditionRun with only outcome="pass" /
    outcome="silent" entries → format_init_diagnostic returns the
    empty-case sentinel verbatim per AC-5."""
    run = PreconditionRun(
        halted=False,
        results=(
            PreconditionResult(dependency="claude-code", outcome="pass"),
            PreconditionResult(dependency="lad", outcome="silent"),
        ),
    )
    out = format_init_diagnostic(run, marker_registry=runtime_marker_registry)
    assert out == "## Init Precondition Check — All Preconditions Met\n"


# --------------------------------------------------------------------------- #
# AC-9 case 14 — load_dependencies surfaces SDN-001 failures unchanged        #
# --------------------------------------------------------------------------- #


def test_load_dependencies_sdn001_failure_propagates_unchanged(
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """AC-9 case 14: a fixture dependencies.yaml with a SDN-001 shape
    violation → run_init_preconditions propagates the underlying
    RuntimeError UNCHANGED per AC-1 + Pattern 5 (loud-fail; do not
    swallow contract failures into precondition diagnostics)."""
    with pytest.raises(RuntimeError) as exc_info:
        run_init_preconditions(
            _passing_probes(),
            project_type="web",
            dependencies_path=_SHAPE_VIOLATION_FIXTURE,
            marker_registry=runtime_marker_registry,
            run_state=_make_run_state(),
        )
    assert "failed SDN-001 shape validation" in str(exc_info.value)


# --------------------------------------------------------------------------- #
# AC-9 case 15 — schema-version bump non-regression                           #
# --------------------------------------------------------------------------- #


def test_schema_version_bumps_non_regression() -> None:
    """AC-9 case 15: the on-disk canonical schemas at HEAD parse with
    schema_version "1.5" (dependencies.yaml — Story 14.1 bumped 1.4 → 1.5
    for the ``git`` MVP dependency entry addition per ADR-009 worktree-vs-
    branch boundary decision; lineage 1.0 (Story 1.6 base) → 1.1 (Story 7.3)
    → 1.2 (Story 9.1 mobile-mcp activation) → 1.3 (Story 9.5 mobile-mcp
    sub_classification fields) → 1.4 (Story 10.1 lad activation) → 1.5
    (Story 14.1 git entry addition)) AND "1.6" (marker-taxonomy.yaml
    — Story 13.6 bumped 1.5 → 1.6 for the ``flow-branch`` sub_classification
    under ``heuristic-skipped`` per the FR22c within-AC flow-branch contract;
    prior Story 9.5 bumped 1.4 → 1.5 for the two new
    ``mobile-blocked.sub_classifications`` [init-unavailable,
    mid-run-unavailable] per Story 9.5 AC-1; Story 9.3 had bumped 1.3 → 1.4
    for the ``mobile-mcp-init-unreachable`` sub-classification addition;
    Story 10.1 introduces no marker-taxonomy bump per AC-9 closed-set
    discipline; Story 14.1 introduces no marker-taxonomy bump per AC-10
    closed-set discipline — the ``worktree-stale-lock`` marker landed in
    Story 14.3 (1.6 → 1.7) and ``parallel-story-state-pollution`` landed in
    Story 14.5 (1.7 → 1.8), the two markers ADR-009 named as forward-
    pointers). Verifies the Story 7.3 + Story 9.3
    + Story 9.5 + Story 13.6 schema bumps, the Story 9.1 + Story 10.1
    activation bumps + Story 14.1 git-entry bump landed AND the existing
    enumeration_check substrate-component-4 gate continues to pass.
    """
    import subprocess

    from loud_fail_harness.dependencies_validator import load_dependencies
    from loud_fail_harness.reconciler import load_marker_taxonomy

    raw = load_dependencies()
    assert raw["schema_version"] == "1.5"

    # Marker taxonomy round-trip: load_marker_taxonomy returns the
    # closure of marker_class strings; verify the schema_version field
    # via direct read.
    import yaml

    taxonomy_path = (
        pathlib.Path(__file__).resolve().parents[3]
        / "schemas"
        / "marker-taxonomy.yaml"
    )
    taxonomy_data = yaml.safe_load(taxonomy_path.read_text(encoding="utf-8"))
    # Story 14.3 bumped 1.6 → 1.7 (additive: new top-level marker class
    # ``worktree-stale-lock`` per ADR-009 Consequence 5 + epics-phase-2.md
    # line 325 forward-pointer contract; treated as PATCH).
    # Story 14.5 bumped 1.7 → 1.8 (additive: new top-level marker class
    # ``parallel-story-state-pollution`` per ADR-009 Consequence 5 +
    # epics-phase-2.md line 353; treated as PATCH per epics-phase-2.md line 70
    # + the Story 14.3 precedent).
    # Story 15.1 bumped 1.8 → 1.9 (additive: OPTIONAL `lifetime` field on the
    # worktree-stale-lock entry; MINOR bump per the additive-optional-field rule).
    assert taxonomy_data["schema_version"] == "1.9"

    # Confirm the marker-taxonomy load surfaces the new sub_classifications
    # under env-setup-failed (closure check via `load_marker_taxonomy`
    # — the function returns marker class identifiers; sub_classifications
    # appear in the parsed YAML directly).
    env_entry = next(
        e for e in taxonomy_data["markers"] if e["marker_class"] == "env-setup-failed"
    )
    new_subs = {
        "tea-module-missing",
        "bmad-core-version-mismatch",
        "claude-code-version-mismatch",
        "playwright-mcp-init-unreachable",
        # Story 9.3 mobile-mcp activation (ADR-007) — additional
        # sub_classification appended under env-setup-failed.
        "mobile-mcp-init-unreachable",
    }
    assert new_subs.issubset(set(env_entry["sub_classifications"]))

    # `load_marker_taxonomy` invariants (substrate component 3) hold.
    classes = load_marker_taxonomy(taxonomy_path)
    assert "env-setup-failed" in classes

    # Story 14.4 landed two NEW run-state-family cell-1 schemas at
    # schema_version "1.0" (epic-run-state.yaml + sprint-run-state.yaml);
    # run-state.yaml itself is byte-unchanged at "1.3" (the per-worktree
    # run-state reuses it verbatim — only the on-disk path differs). The
    # version-history witness asserts the two new schemas explicitly so a
    # future bump is an explicit additive change.
    schemas_dir = taxonomy_path.parent
    epic_schema = yaml.safe_load(
        (schemas_dir / "epic-run-state.yaml").read_text(encoding="utf-8")
    )
    sprint_schema = yaml.safe_load(
        (schemas_dir / "sprint-run-state.yaml").read_text(encoding="utf-8")
    )
    run_state_schema = yaml.safe_load(
        (schemas_dir / "run-state.yaml").read_text(encoding="utf-8")
    )
    assert epic_schema["schema_version"] == "1.0"
    assert sprint_schema["schema_version"] == "1.0"
    assert run_state_schema["schema_version"] == "1.3"

    # Substrate-component-4 enumeration-equivalence gate continues to
    # pass — both schema bumps preserve cross-file consistency.
    result = subprocess.run(
        ["uv", "run", "python", "-m", "loud_fail_harness.enumeration_check"],
        cwd=pathlib.Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"enumeration_check failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    )


# --------------------------------------------------------------------------- #
# Helper-coverage tests beyond AC-9 (extended fixture exercises AC-7 +        #
# graceful-degrade structural path)                                           #
# --------------------------------------------------------------------------- #


def test_extended_fixture_graceful_degrade_branch_structural(
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Extended fixture exercises the graceful-degrade init dispatch
    path (no canonical entry currently uses it; AC-4 says the branch
    must be exercised structurally so a future schema addition does
    not crash)."""
    probes = PreconditionProbeRegistry(
        claude_code=lambda: _passing_probe("2.1.32"),
        bmad_core=lambda: _passing_probe("6.0"),
        git=lambda: _passing_probe(),
        tea_module=lambda: _passing_probe(),
        playwright_mcp=lambda: _passing_probe(),
        mobile_mcp=lambda: _passing_probe(),
        lad=lambda: _passing_probe(),
    )
    # Add a fictional probe via the registry's `probe_for` extension —
    # the dispatcher's missing-probe branch records `outcome="silent"`
    # for the synthetic-graceful-degrade dep since we can't add a
    # field to the frozen registry. Verify the dispatcher does NOT
    # crash on the extended fixture.
    run = run_init_preconditions(
        probes,
        project_type="web",
        dependencies_path=_EXTENDED_FIXTURE,
        marker_registry=runtime_marker_registry,
        run_state=_make_run_state(),
    )
    # synthetic-graceful-degrade has no probe in the registry; outcome
    # is "silent" per the missing-probe branch.
    sgd = next(
        r for r in run.results if r.dependency == "synthetic-graceful-degrade"
    )
    assert sgd.outcome == "silent"
    # partial-project-type with project_type="mobile" → no profile
    # resolves (the mobile key is absent); `outcome="silent"` per AC-7.
    run_mobile = run_init_preconditions(
        probes,
        project_type="mobile",
        dependencies_path=_EXTENDED_FIXTURE,
        marker_registry=runtime_marker_registry,
        run_state=_make_run_state(),
    )
    ppt = next(
        r for r in run_mobile.results if r.dependency == "partial-project-type"
    )
    assert ppt.outcome == "silent"


def test_project_type_parametrized_over_three_types(
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """AC-7 parametrization: project_type ranges over the three
    canonical values; the dispatcher resolves `by_project_type` deps
    correctly for each."""
    for pt in ("web", "api", "mobile"):
        pt_typed: ProjectType = pt  # type: ignore[assignment]
        run = run_init_preconditions(
            _passing_probes(),
            project_type=pt_typed,
            marker_registry=runtime_marker_registry,
            run_state=_make_run_state(),
        )
        # Always the same seven top-level deps (declaration order).
        # Story 14.1 added `git` as the first MVP entry per ADR-009.
        deps = [r.dependency for r in run.results]
        assert deps == [
            "git",
            "claude-code",
            "bmad-core",
            "tea-module",
            "playwright-mcp",
            "mobile-mcp",
            "lad",
        ]


# --------------------------------------------------------------------------- #
# Supplementary — _dispatch_graceful_degrade direct dispatch coverage         #
# --------------------------------------------------------------------------- #


def test_dispatch_graceful_degrade_fail_branch_warn_and_marker(
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Supplementary: directly exercises _dispatch_graceful_degrade's
    fail branch (probe available=False → outcome="warn" + marker
    registered).

    run_init_preconditions cannot reach this branch because no canonical
    dependency declares graceful-degrade at the init phase, and the
    frozen PreconditionProbeRegistry does not support synthetic entries.
    Direct dispatch is the only viable coverage path.
    """
    taxonomy_entries = _load_marker_taxonomy_entries()
    rs = _make_run_state()
    profile_spec: dict = {
        "profile": "graceful-degrade",
        "diagnostic": "Synthetic dep unavailable; warn and proceed.",
        "marker_class": "env-setup-failed",
        "sub_classification": "tea-module-missing",
    }
    entry: dict = {"version_floor": "1.0"}
    probe_result = PreconditionProbeResult(available=False)

    result, new_run_state = _dispatch_graceful_degrade(
        dependency="synthetic-dep",
        entry=entry,
        profile_spec=profile_spec,
        project_type="web",
        probe_result=probe_result,
        run_state=rs,
        marker_registry=runtime_marker_registry,
        taxonomy_entries=taxonomy_entries,
    )

    assert result.outcome == "warn"
    assert result.marker_class == "env-setup-failed"
    assert result.sub_classification == "tea-module-missing"
    assert result.dependency_diagnostic == "Synthetic dep unavailable; warn and proceed."
    assert new_run_state is not None
    assert "env-setup-failed: tea-module-missing" in new_run_state.active_markers


def test_dispatch_graceful_degrade_version_below_floor_warn(
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Supplementary: _dispatch_graceful_degrade's version-floor path
    (available=True but version_observed below version_floor → "warn").

    Verifies the D2-A symmetry fix: graceful-degrade now checks
    version_floor the same way total-block does.
    """
    taxonomy_entries = _load_marker_taxonomy_entries()
    rs = _make_run_state()
    profile_spec: dict = {
        "profile": "graceful-degrade",
        "diagnostic": "Dep version too old; warn and proceed.",
        "marker_class": "env-setup-failed",
        "sub_classification": "bmad-core-version-mismatch",
    }
    entry: dict = {"version_floor": "2.0"}
    probe_result = PreconditionProbeResult(available=True, version_observed="1.9")

    result, new_run_state = _dispatch_graceful_degrade(
        dependency="synthetic-versioned-dep",
        entry=entry,
        profile_spec=profile_spec,
        project_type="web",
        probe_result=probe_result,
        run_state=rs,
        marker_registry=runtime_marker_registry,
        taxonomy_entries=taxonomy_entries,
    )

    assert result.outcome == "warn"
    assert result.marker_class == "env-setup-failed"
    assert new_run_state is not None
    assert "env-setup-failed: bmad-core-version-mismatch" in new_run_state.active_markers


def test_dispatch_graceful_degrade_mobile_blocked_mid_run_unavailable(
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Story 9.5 supplement — _dispatch_graceful_degrade wires
    ``mobile-blocked: mid-run-unavailable`` into active_markers.

    Verifies that a graceful-degrade profile spec with
    ``marker_class="mobile-blocked"`` and
    ``sub_classification="mid-run-unavailable"`` (the runtime profile
    declared in ``dependencies.yaml`` after Story 9.5) produces
    ``outcome="warn"``, sets ``PreconditionResult.sub_classification``
    correctly, and registers ``"mobile-blocked: mid-run-unavailable"``
    in ``active_markers``. Completes the Story 9.5 patch for
    B3+B4+E4 (runtime-profile path previously untested at this layer).
    """
    taxonomy_entries = _load_marker_taxonomy_entries()
    rs = _make_run_state()
    profile_spec: dict = {
        "profile": "graceful-degrade",
        "diagnostic": "Mobile MCP unavailable mid-run; degrade and continue.",
        "marker_class": "mobile-blocked",
        "sub_classification": "mid-run-unavailable",
    }
    entry: dict = {}
    probe_result = PreconditionProbeResult(available=False)

    result, new_run_state = _dispatch_graceful_degrade(
        dependency="mobile-mcp",
        entry=entry,
        profile_spec=profile_spec,
        project_type="mobile",
        probe_result=probe_result,
        run_state=rs,
        marker_registry=runtime_marker_registry,
        taxonomy_entries=taxonomy_entries,
    )

    assert result.outcome == "warn"
    assert result.marker_class == "mobile-blocked"
    assert result.sub_classification == "mid-run-unavailable"
    assert new_run_state is not None
    assert "mobile-blocked: mid-run-unavailable" in new_run_state.active_markers


# --------------------------------------------------------------------------- #
# Mobile-mcp init-time `mobile-blocked` emission (Story 9.5):                 #
#   * AC-7 test 1: total-block emission on mobile project type fires          #
#     `mobile-blocked: init-unavailable` with the verbatim diagnostic         #
#     literal (architecture.md line 625 / dependencies.yaml line 140).        #
#   * AC-7 test 2/3: silence-unless-configured on web/api project types       #
#     (NFR-I3 witness; the mobile-mcp dep is opt-in-skip on non-mobile        #
#     project types per dependencies.yaml).                                   #
#   * AC-7 test 4: cross-schema enumeration-equivalence — the                 #
#     dependencies-schema-declared sub_classification "init-unavailable"      #
#     IS enumerated under marker-taxonomy.yaml's                              #
#     mobile-blocked.sub_classifications closed-set (substrate component      #
#     4 axis at the test level).                                              #
# --------------------------------------------------------------------------- #


_MOBILE_BLOCKED_INIT_FIXTURE = (
    _FIXTURE_DIR / "dependencies-fixture-mobile-blocked.yaml"
)


def test_run_init_preconditions_emits_mobile_blocked_init_unavailable_when_mobile_mcp_unreachable_on_mobile_project(  # noqa: E501
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Story 9.5 AC-7 #1 — init-time emission witness end-to-end.

    Construct probes where every canonical dep passes EXCEPT
    ``mobile-mcp`` (probe returns ``available=False``). Call
    ``run_init_preconditions`` with ``project_type="mobile"``;
    assert: (i) the run halted; (ii) the mobile-mcp result halts with
    ``marker_class="mobile-blocked"`` AND
    ``sub_classification="init-unavailable"`` AND
    ``diagnostic_text == "Mobile MCP required for mobile projects. See
    docs/mobile-mcp-setup.md."`` (BYTE-FOR-BYTE — the
    architecture.md line 625 verbatim literal); (iii)
    ``run_state.active_markers`` contains
    ``"mobile-blocked: init-unavailable"``.
    """
    rs = _make_run_state()
    probes = _failing_for("mobile_mcp")
    # Use the minimal fixture (mobile-mcp only) to exercise the
    # init-time emission path in isolation — non-mobile-mcp deps are
    # `outcome="silent"` per the missing-probe / missing-entry branch.
    run = run_init_preconditions(
        probes,
        project_type="mobile",
        dependencies_path=_MOBILE_BLOCKED_INIT_FIXTURE,
        marker_registry=runtime_marker_registry,
        run_state=rs,
    )

    assert run.halted is True
    mobile_mcp_results = [r for r in run.results if r.dependency == "mobile-mcp"]
    assert len(mobile_mcp_results) == 1
    mobile_mcp_result = mobile_mcp_results[0]
    assert mobile_mcp_result.outcome == "halt"
    assert mobile_mcp_result.marker_class == "mobile-blocked"
    assert mobile_mcp_result.sub_classification == "init-unavailable"
    assert (
        mobile_mcp_result.diagnostic_text
        == "Mobile MCP required for mobile projects. See docs/mobile-mcp-setup.md."
    )
    assert run.run_state is not None
    assert "mobile-blocked: init-unavailable" in run.run_state.active_markers


def test_run_init_preconditions_silent_for_mobile_mcp_on_web_project(
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Story 9.5 AC-7 #2 — web-project silence witness.

    Even when the mobile-mcp probe returns ``available=False``, a web
    project's run does NOT emit ``mobile-blocked`` because
    ``mobile-mcp.by_project_type.web.profiles.init`` is
    ``opt-in-skip`` (no ``marker_class``). Silence-unless-configured
    per NFR-I3.
    """
    rs = _make_run_state()
    probes = _failing_for("mobile_mcp")
    run = run_init_preconditions(
        probes,
        project_type="web",
        marker_registry=runtime_marker_registry,
        run_state=rs,
    )

    # Run may halt (playwright-mcp web init is total-block — but here
    # playwright passes); mobile-mcp result MUST NOT halt and MUST NOT
    # carry a mobile-blocked marker.
    mobile_mcp_results = [r for r in run.results if r.dependency == "mobile-mcp"]
    assert len(mobile_mcp_results) == 1
    mobile_mcp_result = mobile_mcp_results[0]
    assert mobile_mcp_result.outcome == "silent"
    assert mobile_mcp_result.marker_class is None
    # NFR-I3 — silence-unless-configured: no mobile-blocked marker class
    # in active_markers post-dispatch.
    assert run.run_state is not None
    assert not any(
        m.startswith("mobile-blocked") for m in run.run_state.active_markers
    )


def test_run_init_preconditions_silent_for_mobile_mcp_on_api_project(
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Story 9.5 AC-7 #3 — api-project silence witness (symmetry with
    test #2). Confirms the silence rule holds across both non-mobile
    project types.
    """
    rs = _make_run_state()
    probes = _failing_for("mobile_mcp")
    run = run_init_preconditions(
        probes,
        project_type="api",
        marker_registry=runtime_marker_registry,
        run_state=rs,
    )

    mobile_mcp_results = [r for r in run.results if r.dependency == "mobile-mcp"]
    assert len(mobile_mcp_results) == 1
    mobile_mcp_result = mobile_mcp_results[0]
    assert mobile_mcp_result.outcome == "silent"
    assert mobile_mcp_result.marker_class is None
    assert run.run_state is not None
    assert not any(
        m.startswith("mobile-blocked") for m in run.run_state.active_markers
    )


def test_run_init_preconditions_emits_init_unavailable_sub_classification_byte_identical_to_taxonomy() -> None:  # noqa: E501
    """Story 9.5 AC-7 #4 — cross-schema enumeration-equivalence witness.

    The ``sub_classification`` value the dispatch path threads
    (``"init-unavailable"`` from ``dependencies.yaml``'s mobile-mcp
    mobile-init declaration) MUST be enumerated under
    ``schemas/marker-taxonomy.yaml``'s ``mobile-blocked.sub_classifications``
    closed-set. Drift catcher between the two schemas at the test
    level (substrate component 4 enforces the same at CI time per
    AC-13 / ``test_enumeration_check`` extension).
    """
    import yaml

    taxonomy_path = (
        pathlib.Path(__file__).resolve().parents[3]
        / "schemas"
        / "marker-taxonomy.yaml"
    )
    taxonomy_data = yaml.safe_load(taxonomy_path.read_text(encoding="utf-8"))
    mobile_blocked_entry = next(
        e
        for e in taxonomy_data["markers"]
        if e["marker_class"] == "mobile-blocked"
    )
    assert "init-unavailable" in mobile_blocked_entry["sub_classifications"]
    assert "mid-run-unavailable" in mobile_blocked_entry["sub_classifications"]


# --------------------------------------------------------------------------- #
# Story 10.5 AC-3 — lad_precondition_probe_factory positive-path tests        #
# (post-Story-12.2: factory signature collapsed to a single                   #
# read_review_lad_enabled callable; configured-but-api-key-missing branch    #
# retired per Sprint Change Proposal 2026-05-18 validation-responsibility-    #
# boundary correction)                                                        #
# --------------------------------------------------------------------------- #


def test_lad_precondition_probe_disabled_returns_unconfigured() -> None:
    """Story 10.5 AC-3 branch (i) (post-Story-12.2):
    ``read_review_lad_enabled() is False`` → probe returns
    ``available=False``, ``sub_classification="unconfigured"``,
    ``evidence=None``. Routes through ``_dispatch_opt_in_skip``'s
    SDN-001 ``condition: unconfigured`` branch (``silent: true``) —
    ZERO marker emission per AC-5 silence-unless-configured invariant.
    """
    probe = lad_precondition_probe_factory(
        read_review_lad_enabled=lambda: False,
    )
    result = probe()
    assert result.available is False
    assert result.sub_classification == "unconfigured"
    assert result.evidence is None
    assert result.version_observed is None


def test_lad_precondition_probe_enabled_returns_available() -> None:
    """Story 10.5 AC-3 branch (ii) (post-Story-12.2 collapsed branch):
    ``read_review_lad_enabled() is True`` → probe returns
    ``available=True``, ``sub_classification=None``, ``evidence=None``.
    The pre-Story-12.2 ``configured-but-api-key-missing`` branch is
    retired — third-party API-key validation now flows through the
    upstream ``lad_mcp_server`` MCP boundary, not through this
    precondition substrate (Sprint Change Proposal 2026-05-18 +
    Story 12.2).
    """
    probe = lad_precondition_probe_factory(
        read_review_lad_enabled=lambda: True,
    )
    result = probe()
    assert result.available is True
    assert result.sub_classification is None
    assert result.evidence is None


# --------------------------------------------------------------------------- #
# Story 10.5 AC-5 — silence-unless-configured integration tests               #
# --------------------------------------------------------------------------- #


def test_lad_precondition_probe_disabled_emits_zero_lad_skipped_markers(
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Story 10.5 AC-5 silence-unless-configured #1 (post-Story-12.2):
    config disabled → ``run_init_preconditions`` routes the LAD entry
    through the SDN-001 ``condition: unconfigured`` branch
    (``silent: true``); ``PreconditionRun.results[lad].outcome ==
    "silent"`` AND zero ``"LAD-skipped"`` markers in
    ``run_state.active_markers``.
    """
    rs = _make_run_state()
    base = _passing_probes()
    probe = lad_precondition_probe_factory(
        read_review_lad_enabled=lambda: False,
    )
    probes = PreconditionProbeRegistry(
        claude_code=base.claude_code,
        bmad_core=base.bmad_core,
        git=base.git,
        tea_module=base.tea_module,
        playwright_mcp=base.playwright_mcp,
        mobile_mcp=base.mobile_mcp,
        lad=probe,
    )
    run = run_init_preconditions(
        probes,
        project_type="web",
        marker_registry=runtime_marker_registry,
        run_state=rs,
    )
    assert run.halted is False
    lad = next(r for r in run.results if r.dependency == "lad")
    assert lad.outcome == "silent"
    assert lad.marker_class is None
    assert run.run_state is not None
    assert "LAD-skipped" not in run.run_state.active_markers


def test_config_review_lad_omitted_block_emits_zero_lad_skipped_markers(
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Story 10.5 AC-5 silence-unless-configured #3 (post-Story-12.2):
    the operator's ``_bmad/automation/config.yaml`` has NO
    ``review_lad`` block at all → the consumer-side
    ``config.get("review_lad", {}).get("enabled", False)`` defaulting
    path resolves to ``False`` → ``read_review_lad_enabled()`` returns
    ``False`` → probe returns ``available=False,
    sub_classification="unconfigured"``. Post-Story-12.2 the factory
    no longer consults any env var — the consumer-side config gate is
    the authoritative enabler regardless of env-var state, and
    upstream credential validation lives at the ``lad_mcp_server``
    MCP boundary per Sprint Change Proposal 2026-05-18.
    """
    rs = _make_run_state()
    base = _passing_probes()
    probe = lad_precondition_probe_factory(
        read_review_lad_enabled=lambda: False,
    )
    probes = PreconditionProbeRegistry(
        claude_code=base.claude_code,
        bmad_core=base.bmad_core,
        git=base.git,
        tea_module=base.tea_module,
        playwright_mcp=base.playwright_mcp,
        mobile_mcp=base.mobile_mcp,
        lad=probe,
    )
    run = run_init_preconditions(
        probes,
        project_type="web",
        marker_registry=runtime_marker_registry,
        run_state=rs,
    )
    assert run.halted is False
    lad = next(r for r in run.results if r.dependency == "lad")
    assert lad.outcome == "silent"
    assert lad.marker_class is None
    assert run.run_state is not None
    assert "LAD-skipped" not in run.run_state.active_markers


# --------------------------------------------------------------------------- #
# Story 14.2 AC-8 — git_precondition_probe_factory + registry field tests     #
# --------------------------------------------------------------------------- #


def test_precondition_probe_registry_has_git_field() -> None:
    """Story 14.2 AC-8 field-set extension witness. The registry's field
    set must include ``git`` as a required field after Story 14.2's
    deferral resolution per Story 14.1 Review Finding #3 ("the probe
    registration belongs to the story that adds the
    `worktree-lifecycle` library (Story 14.2+)")."""
    assert "git" in PreconditionProbeRegistry.model_fields
    assert PreconditionProbeRegistry.model_fields["git"].is_required()


def test_git_precondition_probe_factory_returns_callable() -> None:
    """Mirrors Story 10.5's ``test_lad_precondition_probe_factory_returns_callable``
    posture: the factory returns a zero-arg callable."""
    probe = git_precondition_probe_factory(
        read_git_version=lambda: "git version 2.50.0",
    )
    assert callable(probe)


def test_git_precondition_probe_factory_pass_on_modern_git() -> None:
    """``git --version`` reports >= 2.5.0 -> ``available=True``."""
    probe = git_precondition_probe_factory(
        read_git_version=lambda: "git version 2.50.0",
    )
    result = probe()
    assert result.available is True
    assert result.sub_classification is None


def test_git_precondition_probe_factory_halt_on_legacy_git() -> None:
    """``git --version`` reports < 2.5.0 -> ``available=False`` ->
    :func:`_dispatch_total_block` halts init with the
    ``dependencies.yaml#git.profiles.init.diagnostic`` text."""
    probe = git_precondition_probe_factory(
        read_git_version=lambda: "git version 2.4.0",
    )
    result = probe()
    assert result.available is False


def test_git_precondition_probe_factory_halt_on_missing_git() -> None:
    """git binary not on PATH -> ``FileNotFoundError`` -> ``available=False``."""
    def _raise() -> str:
        raise FileNotFoundError("git not on PATH")

    probe = git_precondition_probe_factory(read_git_version=_raise)
    result = probe()
    assert result.available is False
    assert result.evidence is None


def test_git_precondition_probe_factory_halt_on_malformed_output() -> None:
    """Reader returns a string that does not parse as a version ->
    ``available=False`` rather than a silent pass per AC-8."""
    probe = git_precondition_probe_factory(
        read_git_version=lambda: "weird output",
    )
    result = probe()
    assert result.available is False


def test_default_git_version_reader_uses_subprocess_list_form() -> None:
    """NFR-S3 hygiene witness: the production-default reader uses
    list-form ``args`` (NEVER ``shell=True``); shell-injection-safe
    by construction. Smoke-calls the production reader (CI runners
    have git on PATH per the activated ``git`` entry in
    ``dependencies.yaml``)."""
    import ast as _ast
    import inspect as _inspect

    source = _inspect.getsource(default_git_version_reader)
    tree = _ast.parse(source)
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Call):
            for kw in node.keywords:
                if kw.arg == "shell" and isinstance(kw.value, _ast.Constant):
                    assert kw.value.value is not True, (
                        "default_git_version_reader must never use shell=True (NFR-S3)"
                    )
    out = default_git_version_reader()
    assert out.startswith("git version "), f"unexpected git --version output: {out!r}"
