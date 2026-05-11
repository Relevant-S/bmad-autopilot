"""Story 9.2 — project-type detection substrate.

Pure-substrate sensor (Pattern 6 + ADR-004 sensor-not-advisor) that
classifies a BMAD project's filesystem layout into one of three
canonical project-type identifiers per
``init_preconditions.ProjectType``: ``web`` | ``api`` | ``mobile``.
The detected value drives Orchestrator dispatch to project-type-
specific QA drivers (Playwright MCP for ``web``, HTTP for ``api``,
mobile MCP for ``mobile``) AND ``dependencies.yaml``'s
``by_project_type`` resolution at init-precondition time.

This module fills the ``<resolved>`` placeholder in
``skills/bmad-automation/steps/init.md`` step 2 — the LLM-runtime
calls :func:`detect_project_type` at the renumbered step 1.5 and
:func:`write_detected_project_type` at step 4's three non-halt
branches (``proceed-fresh`` / ``preserve-merge`` /
``overwrite-confirmed``). See Story 9.2 AC-6 for the exact wiring.

Architectural anchors:

* **Story 9.2** (``_bmad-output/planning-artifacts/epics-phase-1.5.md``
  lines 145-158) — the AC block driving this module.
* **ADR-004 (sensor-not-advisor)** — :func:`detect_project_type`
  returns a structured :class:`DetectionOutcome`; it performs NO
  marker emission, NO stderr writes, NO ``sys.exit`` calls. The
  LLM-runtime is the surface that decides HOW to react to the
  outcome (halt-with-diagnostic vs. proceed-with-detected-value).
* **Pattern 4 (state-update discipline)** —
  :func:`write_detected_project_type` uses the tempfile +
  ``os.replace`` atomic pattern; on a write failure the original
  ``config.yaml`` is byte-identical to the pre-write state. Mirrors
  :func:`loud_fail_harness.init_non_destructive_guard._atomic_write_text`
  byte-for-byte; duplication is intentional per Story 9.2 Dev Notes
  ("sharing code here would over-couple the two surfaces").
* **Pattern 5 (loud-fail doctrine)** — ambiguous detection halts
  ``init`` via stderr diagnostic + non-zero exit at the LLM-runtime
  surface. NO new marker class is emitted; the closed-set marker
  taxonomy v1 (27 classes, ratified in Epic 8 retro per
  ``sprint-status.yaml`` line 38) is preserved. Halting at this
  pre-precondition surface is structurally analogous to
  argv-parse-error and to Story 7.6's ``--overwrite-confirmed``
  parse path — non-marker-emitting init halts that fail BEFORE the
  ``run_state`` machinery is online.
* **Pattern 6 (Pydantic v2 + frozen models + dependency injection)** —
  :class:`DetectionRequest` / :class:`DetectionOutcome` /
  :class:`WriteResult` are frozen Pydantic v2 models with explicit,
  named fields. Mirrors :class:`GuardRequest` /
  :class:`GuardOutcome` shape from Story 7.6.
* **FR62 / Story 1.10a (pluggability)** — this module imports ONLY
  Python stdlib + ``pydantic`` + ``init_preconditions.ProjectType``
  (single source of truth for the Literal). NO imports from any
  specialist-wrapper module (``dev_wrapper`` / ``review_bmad_wrapper``
  / ``qa_ac_iteration`` / ``playwright_driver`` / ``http_driver`` /
  ``bundle_assembly`` / ``specialist_dispatch``).

Detection rule (deterministic precedence — top-to-bottom; first
non-conflicting match wins):

1. **mobile** —
   (``<root>/ios/`` is a directory AND ``<root>/android/`` is a
   directory) — canonical React Native layout, OR
   ``<root>/pubspec.yaml`` exists — Flutter top-level manifest, OR
   ``<root>/app.json`` exists AND its parsed JSON content has a
   top-level ``expo`` OR ``react-native`` key — Expo / RN manifest.
2. **web** — ``<root>/package.json`` exists AND its parsed JSON
   content has any of {``next``, ``react``, ``vue``, ``nuxt``,
   ``svelte``, ``vite``, ``@angular/core``, ``astro``} as a key in
   ``dependencies`` OR ``devDependencies``.
3. **api** — ``<root>/package.json`` has any of {``express``,
   ``fastify``, ``koa``, ``@nestjs/core``, ``hono``} in
   ``dependencies`` OR ``devDependencies``, OR
   ``<root>/pyproject.toml`` parsed content under
   ``[project].dependencies`` OR ``[tool.poetry.dependencies]``
   mentions any of {``fastapi``, ``flask``, ``django``,
   ``starlette``, ``aiohttp``}, OR ``<root>/go.mod`` exists, OR
   ``<root>/Cargo.toml`` exists, OR ``<root>/pom.xml`` OR
   ``<root>/build.gradle`` exists.
4. **ambiguous** — IF the mobile rule fires AND the web OR api
   rule also fires (e.g., a monorepo with ``ios/`` + ``android/``
   AT THE TOP LEVEL AND ``package.json`` carrying a web framework)
   → ``project_type=None``, ``reason="ambiguous"``. The detector
   does NOT silently pick mobile-over-web; the loud-fail halt at
   the LLM-runtime is the contract.
5. **no-indicators** — none of the above match → ``project_type=None``,
   ``reason="no-indicators"``.

The rule is filesystem-driven and TOP-LEVEL only — the detector
does NOT recurse into subdirectories. A ``frontend/ios/`` +
``frontend/android/`` nested mobile app inside an api backend
monorepo is intentionally out of scope at Phase 1.5; the
practitioner sets ``project_type`` explicitly in
``_bmad/automation/config.yaml`` if the layout is non-canonical.

Resolution options (presented verbatim in the ``diagnostic`` field
when ``reason in {"ambiguous", "no-indicators"}`` — canonical
source-of-truth for the user-facing wording, parallel to SDN-001's
"Diagnostic-and-pointer prose source-of-truth" rule for
``dependencies.yaml``-resident diagnostics):

1. Edit ``_bmad/automation/config.yaml`` and set
   ``project_type: <web|api|mobile>`` explicitly under the
   documented field, then re-run ``/bmad-automation init``.
2. Restructure the project root to remove the ambiguity (e.g.,
   move the mobile app into a subdirectory) and re-run
   ``/bmad-automation init``.
3. If the auto-detection rule is wrong for your project layout,
   file an issue at the Automator repo; the rule is filesystem-
   indicator-driven and may need a refinement.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import secrets
import tomllib
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from loud_fail_harness.init_preconditions import ProjectType

__all__ = [
    "DetectionRequest",
    "DetectionOutcome",
    "WriteResult",
    "ProjectType",
    "detect_project_type",
    "write_detected_project_type",
]


# ---------------------------------------------------------------------------
# Framework-name registries (Phase-1.5-MVP baseline; revisit triggers in the
# Story 9.2 Dev Notes "Latest tech information" section).
# ---------------------------------------------------------------------------

_WEB_FRAMEWORK_NAMES: Final[frozenset[str]] = frozenset(
    {
        "next",
        "react",
        "vue",
        "nuxt",
        "svelte",
        "vite",
        "@angular/core",
        "astro",
    }
)
"""Front-end framework package names that trigger ``web``
classification when present in ``package.json`` dependencies or
devDependencies. See AC-2 + module docstring detection-rule step 2.
"""

_NODE_API_FRAMEWORK_NAMES: Final[frozenset[str]] = frozenset(
    {"express", "fastify", "koa", "@nestjs/core", "hono"}
)
"""Node-API framework package names that trigger ``api``
classification when present in ``package.json`` dependencies or
devDependencies.
"""

_MOBILE_PEER_DEPENDENCY_NAMES: Final[frozenset[str]] = frozenset({"react"})
"""``package.json`` dependency names that appear in
``_WEB_FRAMEWORK_NAMES`` but are also universal React Native peer
dependencies.

``react`` is a mandatory peer dep of every React Native project;
treating it as a web-framework signal alongside ``ios/``+``android/``
mobile indicators would make every canonical RN layout fire the
ambiguous halt. When mobile indicators are present these names are
excluded from the web-evidence that drives the ambiguity guard —
they still appear in ``web_evidence`` for transparency but do not
cause a halt.

See Story 9.2 review finding P-01 for context.
"""

_PYTHON_API_FRAMEWORK_NAMES: Final[frozenset[str]] = frozenset(
    {"fastapi", "flask", "django", "starlette", "aiohttp"}
)
"""Python-API framework package names that trigger ``api``
classification when present in ``pyproject.toml`` PEP-621
dependencies or Poetry dependencies.
"""

_OTHER_API_MARKER_FILES: Final[tuple[str, ...]] = (
    "go.mod",
    "Cargo.toml",
    "pom.xml",
    "build.gradle",
)
"""File-existence-only ``api`` markers: Go modules, Rust crate,
Maven, Gradle. See AC-2 step 3.
"""

_PEP621_PACKAGE_NAME_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^([A-Za-z0-9._-]+)"
)
"""Extract the bare package name from a PEP-621 dependency string.

Strips version specifiers, extras, environment markers. Examples:
``"fastapi>=0.100"`` → ``"fastapi"``; ``"fastapi[all]>=0.100"`` →
``"fastapi"``; ``"django ; python_version >= '3.10'"`` → ``"django"``.
"""


# ---------------------------------------------------------------------------
# Diagnostic prose — canonical source-of-truth for the user-facing wording.
# AC-3 binds this prose verbatim; tests assert the three resolution options
# appear in canonical order.
# ---------------------------------------------------------------------------

_AMBIGUOUS_DIAGNOSTIC_HEADER: Final[str] = (
    "init halted: project-type detection is AMBIGUOUS.\n"
    "Multiple project-type indicators were found at the project root, "
    "and the Automator refuses to silently pick one. The conflicting "
    "indicators are listed below; you must resolve the ambiguity before "
    "re-running `/bmad-automation init`."
)

_NO_INDICATORS_DIAGNOSTIC_HEADER: Final[str] = (
    "init halted: project-type detection FAILED.\n"
    "No recognized project-type indicators were found at the project "
    "root, and the Automator refuses to guess. The supported indicator "
    "set is documented in the project_type_detection module docstring; "
    "you must either restructure the project to include a canonical "
    "indicator or set `project_type` explicitly in "
    "`_bmad/automation/config.yaml`."
)

_RESOLUTION_OPTIONS_BLOCK: Final[str] = (
    "Resolution options:\n"
    "  1. Edit `_bmad/automation/config.yaml` and set "
    "`project_type: <web|api|mobile>` explicitly under the documented "
    "field, then re-run `/bmad-automation init`.\n"
    "  2. Restructure the project root to remove the ambiguity "
    "(e.g., move the mobile app into a subdirectory) and re-run "
    "`/bmad-automation init`.\n"
    "  3. If the auto-detection rule is wrong for your project layout, "
    "file an issue at the Automator repo; the rule is auto-detected "
    "from filesystem indicators and may need a refinement."
)


# ---------------------------------------------------------------------------
# Config.yaml line-level helpers — operate on raw text to preserve comments
# and whitespace on round-trip (a YAML round-trip would normalize comments
# and risk Story 7.5 AC-4 cross-reference-line drift).
# ---------------------------------------------------------------------------

_CONFIG_PLACEHOLDER_LINE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^# project_type:.*$", re.MULTILINE
)
"""Match the commented placeholder line in the canonical
``config.yaml.template``. Pattern parallel to the
``# install_method:`` placeholder convention at template lines
87-88. Anchored to start-of-line; the ``re.MULTILINE`` flag scopes
``^`` to line starts within the file body.
"""


# ---------------------------------------------------------------------------
# Pydantic v2 models — Pattern 6 (frozen + explicit fields + field_validator).
# ---------------------------------------------------------------------------


class DetectionRequest(BaseModel):
    """Typed input to :func:`detect_project_type`.

    Pattern 6 — frozen so the LLM-runtime cannot mutate the request
    mid-detection. Mirrors :class:`GuardRequest` (Story 7.6) /
    :class:`StubScaffoldRequest` (Story 7.5) shape.

    Attributes:
        project_root: The practitioner's BMAD project root. The
            detector inspects TOP-LEVEL filesystem indicators under
            this path (no recursion into subdirectories per AC-2).
            REQUIRED; no default. ``is_absolute`` is enforced at
            validation time, mirroring
            ``GuardRequest._project_root_must_be_absolute`` at
            ``init_non_destructive_guard.py:225-231``.
    """

    model_config = ConfigDict(frozen=True)

    project_root: pathlib.Path = Field(
        ...,
        description=(
            "The practitioner's BMAD project root; the detector "
            "inspects top-level filesystem indicators under this path."
        ),
    )

    @field_validator("project_root")
    @classmethod
    def _project_root_must_be_absolute(
        cls, v: pathlib.Path
    ) -> pathlib.Path:
        if not v.is_absolute():
            raise ValueError(
                f"project_root must be an absolute path; got {v!r}. "
                "Pass pathlib.Path.cwd() or a CLI-resolved absolute "
                "path."
            )
        return v


class DetectionOutcome(BaseModel):
    """Typed return of :func:`detect_project_type`.

    Pattern 6 — frozen so the LLM-runtime cannot mutate the outcome
    between read and route.

    Attributes:
        project_type: The detected project-type identifier on
            ``reason="unambiguous"``; ``None`` on ``"ambiguous"`` /
            ``"no-indicators"``. The Literal source-of-truth is
            ``init_preconditions.ProjectType``.
        evidence: Matched filesystem indicators (e.g., ``"ios/"``,
            ``"android/"``, ``"package.json:next"``,
            ``"pyproject.toml:fastapi"``, ``"go.mod"``). Empty list
            on ``reason="no-indicators"``.
        reason: The detection-outcome class. ``"unambiguous"`` =
            exactly one rule fired (mobile alone, web alone, or api
            alone); ``"ambiguous"`` = mobile-plus-(web-or-api)
            conflict; ``"no-indicators"`` = no rule fired.
        diagnostic: Verbatim user-facing prose suitable for stderr
            on the LLM-runtime's halt path. Set when
            ``reason in {"ambiguous", "no-indicators"}``; ``None``
            on ``"unambiguous"``.
    """

    model_config = ConfigDict(frozen=True)

    project_type: ProjectType | None = None
    evidence: list[str] = Field(default_factory=list)
    reason: Literal["unambiguous", "ambiguous", "no-indicators"]
    diagnostic: str | None = None


class WriteResult(BaseModel):
    """Typed return of :func:`write_detected_project_type`.

    Pattern 6 — frozen.

    Attributes:
        action: ``"written"`` on commented-placeholder replacement
            (the canonical ``proceed-fresh`` /
            ``overwrite-confirmed`` branch path);
            ``"preserved"`` on no-op when an existing
            ``project_type`` value is already set (the
            ``preserve-merge`` branch's existing-value-wins
            contract per Story 7.6);
            ``"appended"`` on additive append at end-of-file (the
            ``preserve-merge`` branch's fallback when neither a
            value nor the placeholder is present).
        detected_value: The value passed by the caller (always
            populated for transparency logging).
        existing_value: The pre-existing parsed value when
            ``action="preserved"``; ``None`` otherwise.
        config_path: The resolved target file
            (``<project_root>/_bmad/automation/config.yaml``).
    """

    model_config = ConfigDict(frozen=True)

    action: Literal["written", "preserved", "appended"]
    detected_value: ProjectType
    existing_value: ProjectType | None = None
    config_path: pathlib.Path


# ---------------------------------------------------------------------------
# Public API — sensor (detect) and atomic state-update (write).
# ---------------------------------------------------------------------------


def detect_project_type(request: DetectionRequest) -> DetectionOutcome:
    """Classify ``request.project_root`` into one of ``web`` /
    ``api`` / ``mobile`` / ``ambiguous`` / ``no-indicators``.

    Pure function: reads only top-level filesystem indicators under
    ``request.project_root``; performs NO subprocess calls, NO
    network I/O, NO marker emission, NO stderr writes, NO
    ``sys.exit`` calls. Sensor-not-advisor per ADR-004.

    See the module docstring for the full detection-rule precedence
    and the supported indicator set.
    """
    root = request.project_root

    mobile_evidence: list[str] = []
    web_evidence: list[str] = []
    api_evidence: list[str] = []

    # --- Mobile rule ---
    ios_dir = root / "ios"
    android_dir = root / "android"
    if ios_dir.is_dir() and android_dir.is_dir():
        mobile_evidence.append("ios/")
        mobile_evidence.append("android/")
    if (root / "pubspec.yaml").is_file():
        mobile_evidence.append("pubspec.yaml")
    app_json_path = root / "app.json"
    if app_json_path.exists():
        app_json = _safe_load_json(app_json_path)
        if isinstance(app_json, dict):
            for key in ("expo", "react-native"):
                if key in app_json:
                    mobile_evidence.append(f"app.json:{key}")

    # --- package.json drives web AND api framework matches ---
    package_json_path = root / "package.json"
    if package_json_path.exists():
        package_json = _safe_load_json(package_json_path)
        if isinstance(package_json, dict):
            deps_combined = _merge_node_dependencies(package_json)
            for name in sorted(_WEB_FRAMEWORK_NAMES):
                if name in deps_combined:
                    web_evidence.append(f"package.json:{name}")
            for name in sorted(_NODE_API_FRAMEWORK_NAMES):
                if name in deps_combined:
                    api_evidence.append(f"package.json:{name}")

    # --- pyproject.toml drives the Python-API match ---
    pyproject_path = root / "pyproject.toml"
    if pyproject_path.exists():
        pyproject = _safe_load_toml(pyproject_path)
        if isinstance(pyproject, dict):
            declared = _python_pyproject_packages(pyproject)
            for name in sorted(_PYTHON_API_FRAMEWORK_NAMES):
                if name in declared:
                    api_evidence.append(f"pyproject.toml:{name}")

    # --- Other API markers: file-existence only ---
    for marker in _OTHER_API_MARKER_FILES:
        if (root / marker).is_file():
            api_evidence.append(marker)

    mobile_matched = bool(mobile_evidence)
    web_matched = bool(web_evidence)
    api_matched = bool(api_evidence)

    # P-01 (review fix): "react" is a mandatory React Native peer dep — treating
    # it as a web-framework signal alongside mobile indicators would make every
    # canonical RN project (ios/+android/ + package.json:react) fire the ambiguous
    # halt. Exclude _MOBILE_PEER_DEPENDENCY_NAMES from the ambiguity trigger when
    # mobile is present; the evidence list still contains them for transparency.
    _rn_peer_dep_signals: frozenset[str] = frozenset(
        f"package.json:{n}" for n in _MOBILE_PEER_DEPENDENCY_NAMES
    )
    effective_web_for_ambiguity = web_matched and bool(
        [e for e in web_evidence if e not in _rn_peer_dep_signals]
    )

    if mobile_matched and (effective_web_for_ambiguity or api_matched):
        all_evidence = mobile_evidence + web_evidence + api_evidence
        return DetectionOutcome(
            project_type=None,
            evidence=all_evidence,
            reason="ambiguous",
            diagnostic=_format_ambiguous_diagnostic(all_evidence),
        )

    if mobile_matched:
        return DetectionOutcome(
            project_type="mobile",
            evidence=mobile_evidence,
            reason="unambiguous",
            diagnostic=None,
        )

    if web_matched:
        return DetectionOutcome(
            project_type="web",
            evidence=web_evidence,
            reason="unambiguous",
            diagnostic=None,
        )

    if api_matched:
        return DetectionOutcome(
            project_type="api",
            evidence=api_evidence,
            reason="unambiguous",
            diagnostic=None,
        )

    return DetectionOutcome(
        project_type=None,
        evidence=[],
        reason="no-indicators",
        diagnostic=_format_no_indicators_diagnostic(),
    )


def write_detected_project_type(
    project_root: pathlib.Path,
    project_type: ProjectType,
) -> WriteResult:
    """Record the detected ``project_type`` in
    ``<project_root>/_bmad/automation/config.yaml``.

    Pattern 4 atomic write (tempfile + ``os.replace``) — atomic-on-
    failure means the original ``config.yaml`` is byte-identical to
    the pre-write state if the write process raises mid-flight. NO
    partial writes ever land.

    Branches on the existing file's state (NOT on caller-supplied
    init-branch context; the file's state is the authoritative
    source):

    * If parsed-text inspection finds an existing
      ``project_type: <value>`` non-comment line with a canonical
      Literal value, the helper is a no-op and returns
      ``action="preserved"`` — preserve-merge contract:
      existing-value-wins per Story 7.6.
    * Else if the canonical commented placeholder line is present
      (``# project_type: <set by ...>``, matched by
      ``_CONFIG_PLACEHOLDER_LINE_PATTERN``), the helper replaces it
      with ``project_type: <detected-value>`` (no leading ``#``);
      ``action="written"``. The surrounding comment block is
      preserved (the regex matches a single line, not the
      preceding ``# Source:`` block).
    * Else, the helper appends ``project_type: <detected-value>\\n``
      to the end of the file; ``action="appended"``.

    See AC-5 of Story 9.2 for the full branch-by-branch contract.
    """
    config_path = (
        project_root / "_bmad" / "automation" / "config.yaml"
    ).resolve()

    raw_text = config_path.read_text(encoding="utf-8")
    existing_value = _scan_existing_project_type(raw_text)

    if existing_value is not None:
        return WriteResult(
            action="preserved",
            detected_value=project_type,
            existing_value=existing_value,
            config_path=config_path,
        )

    # P-03 (review fix): if a non-comment project_type: key exists with a
    # non-canonical value (e.g., a user-supplied custom string), treat it as
    # preserved to avoid appending a duplicate key on repeated init runs.
    if _project_type_key_exists(raw_text):
        return WriteResult(
            action="preserved",
            detected_value=project_type,
            existing_value=None,
            config_path=config_path,
        )

    new_line = f"project_type: {project_type}"

    if _CONFIG_PLACEHOLDER_LINE_PATTERN.search(raw_text):
        new_text = _CONFIG_PLACEHOLDER_LINE_PATTERN.sub(
            new_line, raw_text, count=1
        )
        action: Literal["written", "appended"] = "written"
    else:
        suffix = "" if raw_text.endswith("\n") else "\n"
        new_text = f"{raw_text}{suffix}{new_line}\n"
        action = "appended"

    _atomic_write_text(config_path, new_text)

    return WriteResult(
        action=action,
        detected_value=project_type,
        existing_value=None,
        config_path=config_path,
    )


# ---------------------------------------------------------------------------
# Private helpers (parsing + diagnostics + atomic write).
# ---------------------------------------------------------------------------


def _safe_load_json(path: pathlib.Path) -> object:
    """Best-effort JSON load; return ``None`` on parse error or
    ``OSError``. Detection rules degrade gracefully — a malformed
    ``package.json`` simply does not contribute to evidence rather
    than raising; the practitioner's broken-manifest condition will
    surface elsewhere in the toolchain.
    """
    try:
        with path.open("rb") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _safe_load_toml(path: pathlib.Path) -> object:
    """Best-effort TOML load; return ``None`` on parse error or
    ``OSError``. Same graceful-degradation rationale as
    :func:`_safe_load_json`.
    """
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return None


def _merge_node_dependencies(
    package_json: dict[str, object],
) -> set[str]:
    """Return the union of dependency-keys across ``dependencies``
    and ``devDependencies`` in a parsed ``package.json`` mapping.
    """
    keys: set[str] = set()
    for field_name in ("dependencies", "devDependencies"):
        section = package_json.get(field_name)
        if isinstance(section, dict):
            keys.update(str(k) for k in section.keys())
    return keys


def _python_pyproject_packages(
    pyproject: dict[str, object],
) -> set[str]:
    """Return the union of declared package names across PEP-621
    ``[project].dependencies`` (list of strings) and
    ``[tool.poetry.dependencies]`` (mapping). All names are
    normalized to lowercase for case-insensitive matching against
    the canonical framework registries.
    """
    names: set[str] = set()

    project_section = pyproject.get("project")
    if isinstance(project_section, dict):
        deps = project_section.get("dependencies")
        if isinstance(deps, list):
            for spec in deps:
                if isinstance(spec, str):
                    extracted = _extract_pep621_name(spec)
                    if extracted:
                        names.add(extracted.lower())

    tool_section = pyproject.get("tool")
    if isinstance(tool_section, dict):
        poetry_section = tool_section.get("poetry")
        if isinstance(poetry_section, dict):
            poetry_deps = poetry_section.get("dependencies")
            if isinstance(poetry_deps, dict):
                names.update(
                    str(k).lower() for k in poetry_deps.keys()
                )

    return names


def _extract_pep621_name(spec: str) -> str:
    """Strip a PEP-621 dependency-spec string to its bare package
    name (leading alphanumeric / dot / underscore / hyphen run).
    """
    match = _PEP621_PACKAGE_NAME_PATTERN.match(spec.strip())
    return match.group(1) if match else ""


def _scan_existing_project_type(
    raw_text: str,
) -> ProjectType | None:
    """Locate a top-level non-comment ``project_type:`` mapping line
    in the raw config text and return the parsed value if it is one
    of the three canonical Literals.

    Avoids a YAML round-trip to keep imports minimal and preserve
    the file's exact comment / whitespace structure on round-trip.
    A YAML parse would normalize comments and risk the Story 7.5
    AC-4 source-cross-reference-line drift.

    Uses ``line.startswith("project_type:")`` (no ``lstrip``) to
    enforce column-0 matching — indented sub-keys (e.g., a nested
    ``project_type:`` under another mapping) are intentionally
    ignored. See Story 9.2 review finding P-02.
    """
    for line in raw_text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        if line.startswith("project_type:"):
            value = line.split(":", 1)[1].strip().strip("\"'")
            if value == "web":
                return "web"
            if value == "api":
                return "api"
            if value == "mobile":
                return "mobile"
            return None
    return None


def _project_type_key_exists(raw_text: str) -> bool:
    """Return ``True`` if any non-comment top-level ``project_type:``
    key is present in the raw config text, regardless of its value.

    Used by :func:`write_detected_project_type` to prevent appending
    a duplicate ``project_type:`` line when an existing key holds a
    non-canonical (user-supplied custom) value that
    :func:`_scan_existing_project_type` cannot return as a typed
    Literal. See Story 9.2 review finding P-03.
    """
    for line in raw_text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        if line.startswith("project_type:"):
            return True
    return False


def _format_ambiguous_diagnostic(evidence: list[str]) -> str:
    indicator_block = "\n".join(f"  - {item}" for item in evidence)
    return (
        f"{_AMBIGUOUS_DIAGNOSTIC_HEADER}\n\n"
        f"Conflicting indicators:\n{indicator_block}\n\n"
        f"{_RESOLUTION_OPTIONS_BLOCK}"
    )


def _format_no_indicators_diagnostic() -> str:
    return (
        f"{_NO_INDICATORS_DIAGNOSTIC_HEADER}\n\n"
        f"{_RESOLUTION_OPTIONS_BLOCK}"
    )


def _atomic_write_text(path: pathlib.Path, body: str) -> None:
    """Pattern 4 atomic write — temp-file + ``os.replace``.

    Mirrors :func:`loud_fail_harness.init_non_destructive_guard._atomic_write_text`
    byte-for-byte. Per Story 9.2 Dev Notes the duplication is
    intentional: promoting to a shared module would either force a
    cross-specialist import (eroding the Story 1.10a pluggability
    invariant on the way through) or require a substrate-internal
    ``_shared.py`` whose own placement is Phase-2 cleanup territory.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(
        f"{path.name}.tmp.{os.getpid()}.{secrets.token_hex(4)}"
    )
    try:
        fd = os.open(
            temp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644
        )
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(body)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp_path, path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise
