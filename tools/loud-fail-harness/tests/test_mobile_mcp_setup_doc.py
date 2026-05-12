"""Story 9.5 — structural witnesses for ``docs/mobile-mcp-setup.md``.

Contract coverage (Story 9.5 AC-10):

    1. The file exists at ``bmad-autopilot/docs/mobile-mcp-setup.md`` AND
       is non-empty (size > 0 bytes).
    2. The H1 header is exactly ``# Mobile MCP Setup`` AND the canonical
       npm install command from architecture.md line 633 appears verbatim.
    3. LF line endings only (no CR characters; mirrors Stories 2.8 /
       2.9 / 3.5 / 4.1-4.9 / 9.1-9.4 LF-discipline test).
    4. (Drift catcher) ``schemas/dependencies.yaml``'s mobile-mcp
       mobile-init ``diagnostic`` literal references the setup-doc path
       — renaming the doc without updating the schema fails this test
       loudly.
"""

from __future__ import annotations

import pathlib

import yaml


_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_SETUP_DOC_PATH = _REPO_ROOT / "docs" / "mobile-mcp-setup.md"


def test_mobile_mcp_setup_doc_exists() -> None:
    """Story 9.5 AC-10 #1: the operator-facing setup doc lands at the
    canonical path AND has non-zero content."""
    assert _SETUP_DOC_PATH.exists(), (
        f"docs/mobile-mcp-setup.md missing at {_SETUP_DOC_PATH}; "
        "Story 9.5 AC-5 deliverable."
    )
    assert _SETUP_DOC_PATH.stat().st_size > 0, (
        "docs/mobile-mcp-setup.md is empty"
    )


def test_mobile_mcp_setup_doc_referenced_diagnostic_literal_matches_dependencies_schema() -> None:
    """Story 9.5 AC-10 #2: the H1 header is exactly ``# Mobile MCP
    Setup`` AND the canonical npm install command from architecture.md
    line 633 appears verbatim. The install command form is the
    practitioner-facing copy-paste-ready string the doc's "Install +
    connect" section names.
    """
    content = _SETUP_DOC_PATH.read_text(encoding="utf-8")
    assert content.startswith("# Mobile MCP Setup"), (
        "H1 header must be exactly `# Mobile MCP Setup`"
    )
    expected_install = (
        "claude mcp add mobile-mcp -- npx -y @mobilenext/mobile-mcp@latest"
    )
    assert expected_install in content, (
        f"canonical install command (architecture.md line 633) missing "
        f"from setup doc: {expected_install!r}"
    )


def test_mobile_mcp_setup_doc_has_lf_line_endings_only() -> None:
    """Story 9.5 AC-10 #3: LF line endings only (no CR characters)."""
    raw_bytes = _SETUP_DOC_PATH.read_bytes()
    assert b"\r" not in raw_bytes, (
        "docs/mobile-mcp-setup.md contains CR characters; "
        "LF-only discipline (Stories 2.8 / 9.1-9.4) requires LF endings"
    )


def test_dependencies_yaml_init_diagnostic_references_setup_doc_path() -> None:
    """Story 9.5 AC-10 #4 (drift catcher): the ``dependencies.yaml``
    mobile-mcp mobile-init ``diagnostic`` literal contains the
    substring ``"docs/mobile-mcp-setup.md"`` — renaming the doc without
    updating the schema fails this test loudly. The schema-to-doc
    forward reference is structurally enforced.
    """
    deps_path = _REPO_ROOT / "schemas" / "dependencies.yaml"
    deps_data = yaml.safe_load(deps_path.read_text(encoding="utf-8"))
    mobile_init_diag = (
        deps_data["dependencies"]["mobile-mcp"]["by_project_type"]["mobile"][
            "profiles"
        ]["init"]["diagnostic"]
    )
    assert "docs/mobile-mcp-setup.md" in mobile_init_diag, (
        f"dependencies.yaml mobile-mcp init diagnostic does not reference "
        f"the setup doc path: {mobile_init_diag!r}"
    )
