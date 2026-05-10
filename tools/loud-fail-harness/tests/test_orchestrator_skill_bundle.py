"""Skill-bundle structural tests for ``bmad-autopilot/skills/bmad-automation/``
(story 2.5 AC-6).

The dev's-call split (per AC-6's "either tests/test_orchestrator_skill_bundle.py
OR the relevant section of test_orchestrator_run_entry.py — dev's call;
document the choice in Completion Notes"): a SEPARATE FILE here, parallel
to the substrate-helper test layout (one test file per module / one test
file per skill bundle). Rationale: the skill-bundle tests are
text-shape-against-markdown-files; the orchestrator-helper tests are
behavior-shape-against-Python-API. Different test surfaces; different
files.

Tests are STRUCTURAL — file existence + section presence + frontmatter
parsing. They do NOT verify the prose's correctness against the AC-2 /
AC-3 / AC-4 prose verbatim (such verification would require an LLM-grade
content match and is out of scope for unit tests; the prose's correctness
is review-enforced per the FR65 audit doctrine, NOT CI-enforced).

This docstring IS the contract-coverage checklist required by AC-6.

Existence tests:
    [x] SKILL.md, workflow.md, steps/{run,status,resume,init}.md, data/.gitkeep
        → test_skill_bundle_files_exist[*]

SKILL.md frontmatter test:
    [x] frontmatter parses; name == "bmad-automation"; description names
        the four slash commands; body == canonical "Follow the
        instructions in ./workflow.md."
        → test_skill_md_frontmatter_and_body

workflow.md section presence test:
    [x] all four required headings appear (# BMAD Automator Orchestrator
        Workflow, ## Goal, ## Subcommand routing, ## Cross-references)
        → test_workflow_md_required_headings

workflow.md subcommand-routing test:
    [x] Subcommand routing section names all four slash commands AND
        references all four steps/<command>.md files
        → test_workflow_md_subcommand_routing

steps/run.md AC-2 entry-sequence presence test:
    [x] run.md mentions the (a)-(f) labels AND references
        orchestrator_run_entry.py
        → test_run_md_entry_sequence_labels

steps/{status,resume,init}.md stub-discipline tests:
    [x] STUB heading + zero functional logic + binding-stories names
        → test_stub_md_discipline[*]

find_repo_root() discipline test:
    [x] this test module's top-level imports do NOT call find_repo_root
        → test_find_repo_root_not_at_module_collection_time
"""

from __future__ import annotations

import inspect
import pathlib
import re
import sys

import pytest
import yaml

from loud_fail_harness._shared import find_repo_root


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def skill_bundle_root() -> pathlib.Path:
    """Module-scoped resolver of the skill bundle directory.

    ``find_repo_root()`` is called inside the fixture body (function scope at
    setup time), NOT at module import time — Epic 1 retro Action #1
    discipline. The returned path is the inner-repo's
    ``skills/bmad-automation/`` directory per architecture.md View 1.
    """
    return find_repo_root() / "skills" / "bmad-automation"


# --------------------------------------------------------------------------- #
# Existence tests                                                             #
# --------------------------------------------------------------------------- #


_REQUIRED_FILES: list[str] = [
    "SKILL.md",
    "workflow.md",
    "steps/run.md",
    "steps/status.md",
    "steps/resume.md",
    "steps/init.md",
    "data/.gitkeep",
]


@pytest.mark.parametrize("relative_path", _REQUIRED_FILES)
def test_skill_bundle_files_exist(
    skill_bundle_root: pathlib.Path, relative_path: str
) -> None:
    target = skill_bundle_root / relative_path
    assert target.exists(), (
        f"required skill-bundle file missing: {target} "
        f"(per AC-1 of Story 2.5)"
    )


# --------------------------------------------------------------------------- #
# SKILL.md frontmatter test                                                   #
# --------------------------------------------------------------------------- #


_FRONTMATTER_RE = re.compile(
    r"^---\n(?P<frontmatter>.*?)\n---\n(?P<body>.*)\Z", re.DOTALL
)


def test_skill_md_frontmatter_and_body(skill_bundle_root: pathlib.Path) -> None:
    skill_md = (skill_bundle_root / "SKILL.md").read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(skill_md)
    assert match is not None, "SKILL.md must have YAML frontmatter"

    frontmatter = yaml.safe_load(match.group("frontmatter"))
    assert frontmatter["name"] == "bmad-automation"
    description = frontmatter["description"]
    for command in ("run", "status", "resume", "init"):
        assert command in description, (
            f"SKILL.md description must name slash command {command!r}; got: "
            f"{description!r}"
        )

    body = match.group("body").strip()
    assert body == "Follow the instructions in ./workflow.md.", (
        f"SKILL.md body must be the canonical 'Follow the instructions in "
        f"./workflow.md.' (per BMAD-core SKILL.md shape); got: {body!r}"
    )


# --------------------------------------------------------------------------- #
# workflow.md section presence + subcommand-routing tests                     #
# --------------------------------------------------------------------------- #


_WORKFLOW_REQUIRED_HEADINGS: list[str] = [
    "# BMAD Automator Orchestrator Workflow",
    "## Goal",
    "## Subcommand routing",
    "## Cross-references",
]


def test_workflow_md_required_headings(skill_bundle_root: pathlib.Path) -> None:
    workflow_md = (skill_bundle_root / "workflow.md").read_text(encoding="utf-8")
    for heading in _WORKFLOW_REQUIRED_HEADINGS:
        assert heading in workflow_md, (
            f"workflow.md missing required heading: {heading!r} (per AC-1)"
        )


def test_workflow_md_subcommand_routing(
    skill_bundle_root: pathlib.Path,
) -> None:
    workflow_md = (skill_bundle_root / "workflow.md").read_text(encoding="utf-8")
    # Slice out the Subcommand routing section body (heading-to-next-heading
    # or EOF).
    section_anchor = "## Subcommand routing"
    assert section_anchor in workflow_md
    section_start = workflow_md.index(section_anchor) + len(section_anchor)
    rest = workflow_md[section_start:]
    next_section_match = re.search(r"^## ", rest, re.MULTILINE)
    section_body = (
        rest if next_section_match is None else rest[: next_section_match.start()]
    )

    for command in ("run", "status", "resume", "init"):
        assert command in section_body, (
            f"Subcommand routing section must name {command!r}"
        )
    for step_path in ("steps/run.md", "steps/status.md", "steps/resume.md", "steps/init.md"):
        assert step_path in section_body, (
            f"Subcommand routing section must reference {step_path!r}"
        )


# --------------------------------------------------------------------------- #
# steps/run.md AC-2 entry-sequence presence test                              #
# --------------------------------------------------------------------------- #


def test_run_md_entry_sequence_labels(
    skill_bundle_root: pathlib.Path,
) -> None:
    run_md = (skill_bundle_root / "steps" / "run.md").read_text(encoding="utf-8")
    for label in ("(a)", "(b)", "(c)", "(d)", "(e)", "(f)"):
        assert label in run_md, (
            f"steps/run.md must name entry-sequence step {label} (per AC-2)"
        )
    assert "orchestrator_run_entry.py" in run_md, (
        "steps/run.md must cross-reference orchestrator_run_entry.py "
        "(the canonical Python composition per AC-2)"
    )


# --------------------------------------------------------------------------- #
# Stub-discipline tests                                                       #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "stub_name,binding_stories,binding_epic",
    [
        # `status` was removed from the literal-stub gate by Story 8.4 — the
        # stub thickened in place into a runtime-protocol per the verbatim
        # epic AC at `epics.md` lines 3300-3329 (REPLACE the "not yet
        # implemented" + "zero functional logic" paragraphs with the
        # thickened protocol). Story 8.4's `test_status_md_runtime_protocol_present`
        # below is the successor structural-witness for the post-thickening shape.
        #
        # `resume` was removed from the literal-stub gate by Story 8.3 — the
        # stub thickened in place into a runtime-protocol per the verbatim
        # epic AC at `epics.md` lines 3272-3298 (REPLACE the "not yet
        # implemented" + "zero functional logic" paragraphs with the
        # thickened protocol). Story 8.3's `test_resume_md_runtime_protocol_present`
        # below is the successor structural-witness for the post-thickening shape.
        #
        # `init` was removed from the literal-stub gate by Story 7.6 — the
        # stub thickened in place into a runtime-protocol per the verbatim
        # epic AC at `epics.md` line 3068 (REPLACE the "not yet implemented"
        # + "zero functional logic" paragraphs with the thickened protocol).
        # Story 7.6's `test_init_md_runtime_protocol_present` below is the
        # successor structural-witness for the post-thickening shape.
    ],
)
def test_stub_md_discipline(
    skill_bundle_root: pathlib.Path,
    stub_name: str,
    binding_stories: tuple[str, ...],
    binding_epic: int,
) -> None:
    stub_md = (skill_bundle_root / "steps" / f"{stub_name}.md").read_text(
        encoding="utf-8"
    )
    # Top-level heading naming the binding epic.
    assert f"# /bmad-automation {stub_name} — STUB (Epic {binding_epic} thickening)" in stub_md, (
        f"steps/{stub_name}.md must carry the canonical STUB heading per AC-1"
    )
    # Binding-stories listed.
    for story in binding_stories:
        assert story in stub_md, (
            f"steps/{stub_name}.md must name binding story {story}"
        )
    # "Zero functional logic" sentence verbatim.
    assert "zero functional logic" in stub_md, (
        f"steps/{stub_name}.md must include the literal-stub disclaimer "
        f"'zero functional logic' (per AC-1's literal-stub posture)"
    )


def test_init_md_runtime_protocol_present(
    skill_bundle_root: pathlib.Path,
) -> None:
    """Story 7.6 thickened ``steps/init.md`` from a literal stub into a
    runtime-protocol that composes the Story 7.3 / 7.4 / 7.5 substrate
    + the new Story 7.6 non-destructive guard. The structural witness:

    * the canonical STUB heading is preserved (Stories 7.7-7.9 still
      cite `init.md` as Epic-7 work-in-progress),
    * the five Story 7.2-7.5 augmentation lines are preserved as the
      audit trail,
    * the new Story-7.6 augmentation line is present,
    * the literal "not yet implemented" message has been REMOVED,
    * the "zero functional logic" disclaimer has been REMOVED,
    * the runtime-protocol checklist references the four
      ``GuardOutcome.action`` branches by name,
    * the Story 7.8 placeholder is present so future thickeners
      can locate the next surface.
    """
    init_md = (skill_bundle_root / "steps" / "init.md").read_text(encoding="utf-8")

    # Canonical heading retained.
    assert "# /bmad-automation init — STUB (Epic 7 thickening)" in init_md
    # Five augmentation lines preserved as the audit trail.
    for landing_year_marker in (
        "[Story 7.2 landed",
        "[Story 7.3 landed",
        "[Story 7.4 landed",
        "[Story 7.5 landed",
        "[Story 7.6 landed",
    ):
        assert landing_year_marker in init_md, (
            f"steps/init.md must preserve {landing_year_marker!r} as the "
            "audit-trail line for the Epic-7 build-order"
        )
    # The pre-thickening "not yet implemented" message must be GONE.
    assert "is not yet implemented" not in init_md, (
        "steps/init.md must REPLACE the 'not yet implemented' message "
        "with the thickened runtime-protocol per Story 7.6 AC-6"
    )
    # The pre-thickening "zero functional logic" disclaimer must be GONE.
    assert "zero functional logic" not in init_md, (
        "steps/init.md must REPLACE the 'zero functional logic' disclaimer "
        "with the thickened runtime-protocol per Story 7.6 AC-6"
    )
    # Runtime-protocol references the four GuardOutcome.action branches.
    for action in (
        "proceed-fresh",
        "preserve-merge",
        "overwrite-confirmed",
        "halt-would-destroy",
    ):
        assert action in init_md, (
            f"steps/init.md runtime-protocol must reference the "
            f"{action!r} GuardOutcome branch per Story 7.6 AC-6"
        )
    # Story 7.8 placeholder is present so the next thickener can find it.
    assert "Story 7.8" in init_md and "placeholder" in init_md.lower()


def test_resume_md_runtime_protocol_present(
    skill_bundle_root: pathlib.Path,
) -> None:
    """Story 8.3 thickened ``steps/resume.md`` from a literal stub into a
    runtime-protocol that composes the Story 8.2 ``cross_state_recovery``
    substrate + Story 8.3's ``resume_command`` substrate. The structural
    witness:

    * the literal "not yet implemented" message has been REMOVED,
    * the "zero functional logic" disclaimer has been REMOVED,
    * the substrate-invocation `uv run bmad-automation-resume` is named,
    * the four ``ResumeOutcome.action`` branches are referenced by name,
    * cross-references to ``resume_command.py``,
      ``cross_state_recovery.py``, ``lifecycle_state_machine.py``, and
      ``steps/dispatch.md`` are present.
    """
    resume_md = (
        skill_bundle_root / "steps" / "resume.md"
    ).read_text(encoding="utf-8")

    # The pre-thickening stub messages must be GONE per Story 8.3 AC-7.
    assert "is not yet implemented" not in resume_md, (
        "steps/resume.md must REPLACE the 'not yet implemented' message "
        "with the thickened runtime-protocol per Story 8.3 AC-7"
    )
    assert "zero functional logic" not in resume_md, (
        "steps/resume.md must REPLACE the 'zero functional logic' disclaimer "
        "with the thickened runtime-protocol per Story 8.3 AC-7"
    )

    # Substrate invocation named per Story 8.3 AC-7.
    assert "bmad-automation-resume" in resume_md, (
        "steps/resume.md must name the bmad-automation-resume CLI per Story 8.3 AC-7"
    )

    # The four ResumeOutcome.action branches referenced by name.
    for action in (
        "resume-dispatch",
        "resume-already-terminal",
        "resume-conflict-halt",
        "resume-no-run-state",
    ):
        assert action in resume_md, (
            f"steps/resume.md runtime-protocol must reference the "
            f"{action!r} ResumeOutcome branch per Story 8.3 AC-7"
        )

    # Cross-references to the substrate libraries + dispatch step.
    for reference in (
        "resume_command.py",
        "cross_state_recovery.py",
        "lifecycle_state_machine.py",
        "steps/dispatch.md",
    ):
        assert reference in resume_md, (
            f"steps/resume.md must cross-reference {reference!r} per Story 8.3 AC-7"
        )


def test_status_md_runtime_protocol_present(
    skill_bundle_root: pathlib.Path,
) -> None:
    """Story 8.4 thickened ``steps/status.md`` from a literal stub into
    a runtime-protocol that composes the Story 8.4 ``status_command``
    substrate (which itself composes Story 8.2's
    ``_load_run_state_from_disk`` + Story 5.5's
    ``retry_history.resolve_retry_round`` + Story 2.6's
    ``LOG_PATH_TEMPLATE``). The structural witness:

    * the literal "not yet implemented" message has been REMOVED,
    * the "zero functional logic" disclaimer has been REMOVED,
    * the substrate-invocation `uv run bmad-automation-status` is named,
    * the two ``StatusOutcome.action`` branches are referenced by name,
    * the "No mutation invariant" section heading is present (the
      read-only invariant per NFR-O4),
    * cross-references to ``status_command.py``,
      ``cross_state_recovery.py``, ``retry_history.py``, and the
      Story 8.5 multi-story listing are present.
    """
    status_md = (
        skill_bundle_root / "steps" / "status.md"
    ).read_text(encoding="utf-8")

    # The pre-thickening stub messages must be GONE per Story 8.4 AC-7.
    assert "is not yet implemented" not in status_md, (
        "steps/status.md must REPLACE the 'not yet implemented' message "
        "with the thickened runtime-protocol per Story 8.4 AC-7"
    )
    assert "zero functional logic" not in status_md, (
        "steps/status.md must REPLACE the 'zero functional logic' disclaimer "
        "with the thickened runtime-protocol per Story 8.4 AC-7"
    )

    # Substrate invocation named per Story 8.4 AC-7.
    assert "bmad-automation-status" in status_md, (
        "steps/status.md must name the bmad-automation-status CLI per "
        "Story 8.4 AC-7"
    )
    assert "uv --directory" in status_md, (
        "steps/status.md must show the uv --directory invocation pattern "
        "per Story 8.4 AC-7"
    )

    # The two StatusOutcome.action branches referenced by name.
    for action in ("status-found", "status-no-run-state"):
        assert action in status_md, (
            f"steps/status.md runtime-protocol must reference the "
            f"{action!r} StatusOutcome branch per Story 8.4 AC-7"
        )

    # The No-mutation-invariant section heading per Story 8.4 AC-7.
    assert "## No mutation invariant" in status_md, (
        "steps/status.md must carry the 'No mutation invariant' section "
        "heading per Story 8.4 AC-7"
    )

    # Cross-references to the substrate libraries + Story 8.5.
    for reference in (
        "status_command.py",
        "cross_state_recovery.py",
        "retry_history.py",
        "Story 8.5",
    ):
        assert reference in status_md, (
            f"steps/status.md must cross-reference {reference!r} per "
            f"Story 8.4 AC-7"
        )


def test_status_md_no_args_branch_present(
    skill_bundle_root: pathlib.Path,
) -> None:
    """Story 8.5 thickened ``steps/status.md`` with the no-args branch
    dispatch protocol.

    Structural witness per Story 8.5 AC-7:

    * ``## Branch on argument presence`` section header is present
      (the dispatch routing between with-id and no-args branches);
    * the new no-args CLI ``bmad-automation-status-list`` is named;
    * the ``## No-args multi-story listing protocol`` section header
      is present;
    * the two ``ListingOutcome.action`` branches are referenced by
      name (``listing-found``, ``listing-empty``);
    * cross-references to ``multi_story_status.py`` AND the marker-
      taxonomy line for ``orphan-run-state-detected`` are present.
    """
    status_md = (
        skill_bundle_root / "steps" / "status.md"
    ).read_text(encoding="utf-8")

    assert "## Branch on argument presence" in status_md, (
        "steps/status.md must carry the '## Branch on argument presence' "
        "section heading per Story 8.5 AC-7"
    )
    assert "bmad-automation-status-list" in status_md, (
        "steps/status.md must name the bmad-automation-status-list CLI "
        "per Story 8.5 AC-7"
    )
    assert "## No-args multi-story listing protocol" in status_md, (
        "steps/status.md must carry the no-args multi-story listing "
        "protocol section heading per Story 8.5 AC-7"
    )
    for action in ("listing-found", "listing-empty"):
        assert action in status_md, (
            f"steps/status.md no-args runtime-protocol must reference "
            f"the {action!r} ListingOutcome branch per Story 8.5 AC-7"
        )
    for reference in (
        "multi_story_status.py",
        "marker-taxonomy.yaml:382",
        "_bmad-output/planning-artifacts/epics.md:3331-3363",
    ):
        assert reference in status_md, (
            f"steps/status.md must cross-reference {reference!r} per "
            f"Story 8.5 AC-7"
        )


# --------------------------------------------------------------------------- #
# find_repo_root() discipline test                                            #
# --------------------------------------------------------------------------- #


def test_find_repo_root_not_at_module_collection_time() -> None:
    """The test module's TOP-LEVEL imports do NOT call ``find_repo_root``.

    Epic 1 retro Action #1: ``find_repo_root()`` raises ``RuntimeError``
    when invoked outside a repo, so calling it at module import time
    breaks pytest collection in alien environments. The fixture
    :func:`skill_bundle_root` calls it at fixture-setup time only.
    """
    src = inspect.getsource(sys.modules[__name__])
    # Strip the module docstring, then look for find_repo_root() invocations
    # OUTSIDE function/method bodies. Crude but sufficient: the only top-
    # level statements should be imports + parametrize lists + fixture +
    # test definitions. The fixture's call site is INSIDE the fixture body.
    # Verify by parsing top-level statements.
    import ast

    tree = ast.parse(src)
    for node in tree.body:
        # We allow Import / ImportFrom / Assign / FunctionDef / AsyncFunctionDef
        # / ClassDef / Expr (for module docstring). We forbid any Call to
        # find_repo_root at the top level.
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            func = node.value.func
            name = (
                func.attr
                if isinstance(func, ast.Attribute)
                else func.id
                if isinstance(func, ast.Name)
                else None
            )
            assert name != "find_repo_root", (
                "find_repo_root() must not be called at module collection "
                "time; use a fixture per Epic 1 retro Action #1"
            )


# --------------------------------------------------------------------------- #
# Story 2.12 AC-6 — streaming substrate wiring presence test                  #
# --------------------------------------------------------------------------- #


def test_run_step_names_make_event_log_appender(
    skill_bundle_root: pathlib.Path,
) -> None:
    """Story 2.12 AC-6: ``steps/run.md`` names the streaming substrate.

    Structural assertion that the wiring landed in prose: the file
    references both ``make_event_log_appender`` (the appender factory)
    and ``default_event_log_path`` (the canonical path resolver) from
    Story 2.12's :mod:`loud_fail_harness.event_streaming` substrate.
    NOT a behavioral test of LLM-runtime execution — that's the
    practitioner's domain at run time.
    """
    run_md = (skill_bundle_root / "steps" / "run.md").read_text(encoding="utf-8")
    assert "make_event_log_appender" in run_md, (
        "steps/run.md must name make_event_log_appender (Story 2.12 AC-6 wiring)"
    )
    assert "default_event_log_path" in run_md, (
        "steps/run.md must name default_event_log_path (Story 2.12 AC-6 wiring)"
    )
    assert "event_streaming" in run_md, (
        "steps/run.md must cross-reference the event_streaming substrate "
        "module (Story 2.12 AC-6 wiring)"
    )


def test_workflow_md_references_event_streaming_substrate(
    skill_bundle_root: pathlib.Path,
) -> None:
    """Story 2.12 AC-6: ``workflow.md`` cross-references the streaming substrate."""
    workflow_md = (skill_bundle_root / "workflow.md").read_text(encoding="utf-8")
    assert "event_streaming.py" in workflow_md, (
        "workflow.md must cross-reference event_streaming.py (Story 2.12 AC-6)"
    )
    assert "make_event_log_appender" in workflow_md, (
        "workflow.md must name make_event_log_appender (Story 2.12 AC-6)"
    )
