"""Tests for the Story 7.2 install-path module.

Covers AC-7 — eleven independent test functions covering:

* path-priority logic for all three Story 7.1 outcomes (with + without the
  ``--use-plugin-experimental`` opt-in flag),
* audit-doc-drift loud-fails (no-match + multiple-match),
* ``record_install_method`` happy paths (existing config + non-existent
  config), atomicity (mid-write crash simulation), and idempotence,
* plugin-manifest schema validity (JSON parse + ``name`` kebab-case).
"""

from __future__ import annotations

import json
import pathlib
import warnings

import pytest

from loud_fail_harness.install_path import (
    PLUGIN_NAME_PATTERN,
    InstallMethod,
    InstallPathConfigError,
    parse_spike_outcome,
    record_install_method,
    resolve_install_method,
)

# Fixtures live alongside this test module; mirror the existing fixture-
# directory convention established by Stories 1.7+.
_FIXTURE_DIR = pathlib.Path(__file__).resolve().parent / "fixtures" / "install_path"

# Inner-repo root — used to locate the shipped plugin manifest for the
# schema-validity test (AC-7 item 11). Mirrors `_inner_repo_root` in the
# install_path module: the test file lives at
# `bmad-autopilot/tools/loud-fail-harness/tests/test_install_path.py`
# so `parents[3]` is the inner-repo root `bmad-autopilot/`.
_INNER_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# AC-7 item 1 — outcome-1 path priority.
# ---------------------------------------------------------------------------


def test_outcome_1_path_priority() -> None:
    """Outcome 1: `resolve_install_method` returns "plugin" with OR without
    the opt-in flag; the flag is a no-op when plugin is already primary."""
    fixture = _FIXTURE_DIR / "outcome-1-fixture.md"

    method_default = resolve_install_method(audit_doc_path=fixture)
    assert isinstance(method_default, InstallMethod)
    assert method_default.root == "plugin"

    # The flag should be a no-op under outcome 1; no warning expected (the
    # warning is the experimental-opt-in signal, which doesn't apply when
    # the path is already plugin-primary).
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        method_with_flag = resolve_install_method(
            use_plugin_experimental=True, audit_doc_path=fixture
        )
    assert method_with_flag.root == "plugin"


# ---------------------------------------------------------------------------
# AC-7 item 2 — outcome-2 path priority (default; no flag).
# ---------------------------------------------------------------------------


def test_outcome_2_path_priority_default() -> None:
    """Outcome 2 (no flag): returns "git-clone-symlink" — the documented
    primary install path under Story 7.1 outcome 2."""
    fixture = _FIXTURE_DIR / "outcome-2-fixture.md"

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        method = resolve_install_method(audit_doc_path=fixture)
    assert method.root == "git-clone-symlink"


# ---------------------------------------------------------------------------
# AC-7 item 3 — outcome-2 path priority (with flag); structured warning.
# ---------------------------------------------------------------------------


def test_outcome_2_path_priority_with_flag() -> None:
    """Outcome 2 + opt-in flag: returns "plugin" AND emits a structured
    warning naming the experimental opt-in + the per-convention row."""
    fixture = _FIXTURE_DIR / "outcome-2-fixture.md"

    with pytest.warns(UserWarning) as record:
        method = resolve_install_method(
            use_plugin_experimental=True, audit_doc_path=fixture
        )

    assert method.root == "plugin"
    assert len(record) == 1
    message = str(record[0].message)
    assert "experimental" in message.lower()
    assert "Story 7.1 outcome 2" in message
    assert "extension-audit.md" in message


# ---------------------------------------------------------------------------
# AC-7 item 4 — outcome-3 path priority (default + flag-raises).
# ---------------------------------------------------------------------------


def test_outcome_3_path_priority() -> None:
    """Outcome 3 (no flag): returns "git-clone-symlink".
    Outcome 3 (with flag): raises `InstallPathConfigError` because the
    primitive is unavailable."""
    fixture = _FIXTURE_DIR / "outcome-3-fixture.md"

    method_default = resolve_install_method(audit_doc_path=fixture)
    assert method_default.root == "git-clone-symlink"

    with pytest.raises(InstallPathConfigError) as excinfo:
        resolve_install_method(use_plugin_experimental=True, audit_doc_path=fixture)
    assert excinfo.value.invariant == "flag-on-deferred-outcome"
    assert "deferred" in excinfo.value.diagnostic.lower()


# ---------------------------------------------------------------------------
# AC-7 item 5 — audit-doc parse loud-fail (no match).
# ---------------------------------------------------------------------------


def test_audit_doc_loud_fail_no_match() -> None:
    """Audit doc with NO canonical outcome string → `InstallPathConfigError`
    with `invariant="audit-doc-drift"`."""
    fixture = _FIXTURE_DIR / "no-match-fixture.md"

    with pytest.raises(InstallPathConfigError) as excinfo:
        parse_spike_outcome(fixture)
    assert excinfo.value.invariant == "audit-doc-drift"
    assert "NONE" in excinfo.value.diagnostic


# ---------------------------------------------------------------------------
# AC-7 item 6 — audit-doc parse loud-fail (multiple match).
# ---------------------------------------------------------------------------


def test_audit_doc_loud_fail_multiple_match() -> None:
    """Audit doc with TWO canonical outcome strings → `InstallPathConfigError`
    with `invariant="audit-doc-drift"`."""
    fixture = _FIXTURE_DIR / "multiple-match-fixture.md"

    with pytest.raises(InstallPathConfigError) as excinfo:
        parse_spike_outcome(fixture)
    assert excinfo.value.invariant == "audit-doc-drift"
    assert "MULTIPLE" in excinfo.value.diagnostic


# ---------------------------------------------------------------------------
# AC-7 item 7 — record_install_method happy path (existing config).
# ---------------------------------------------------------------------------


def test_record_install_method_existing_config(tmp_path: pathlib.Path) -> None:
    """Existing config keys + comments are preserved on round-trip; the
    `install_method` key is added at top level."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        # ruamel.yaml round-trip mode preserves these comments + key order.
        "# User-managed automation config (FR42 — survives re-installs).\n"
        "retry_budget: 5  # per-story retry ceiling\n"
        "per_story_cost_ceiling_usd: 10.0\n",
        encoding="utf-8",
    )

    record_install_method(InstallMethod("git-clone-symlink"), config_path)

    body = config_path.read_text(encoding="utf-8")
    # All pre-existing keys preserved.
    assert "retry_budget: 5" in body
    assert "per_story_cost_ceiling_usd: 10.0" in body
    # Pre-existing comments preserved (round-trip discipline).
    assert "FR42" in body
    assert "per-story retry ceiling" in body
    # New key added.
    assert "install_method: git-clone-symlink" in body


# ---------------------------------------------------------------------------
# AC-7 item 8 — record_install_method happy path (no config).
# ---------------------------------------------------------------------------


def test_record_install_method_no_config(tmp_path: pathlib.Path) -> None:
    """Non-existent config path → file is created with `install_method` as
    the only top-level key."""
    config_path = tmp_path / "subdir" / "config.yaml"
    assert not config_path.exists()

    record_install_method(InstallMethod("plugin"), config_path)

    assert config_path.exists()
    body = config_path.read_text(encoding="utf-8").strip()
    assert body == "install_method: plugin"


# ---------------------------------------------------------------------------
# AC-7 item 9 — record_install_method atomicity (mid-write crash).
# ---------------------------------------------------------------------------


def test_record_install_method_atomicity(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulated mid-write crash: `os.replace` raises OSError. The original
    config is preserved intact; the temp file is unlinked; no partial
    config replaces the original."""
    from loud_fail_harness import install_path as _install_path

    config_path = tmp_path / "config.yaml"
    original_body = "install_method: plugin\nretry_budget: 5\n"
    config_path.write_text(original_body, encoding="utf-8")

    def boom(src: str, dst: str) -> None:
        raise OSError("simulated mid-rename failure")

    monkeypatch.setattr(_install_path.os, "replace", boom)

    with pytest.raises(OSError, match="simulated mid-rename failure"):
        record_install_method(InstallMethod("git-clone-symlink"), config_path)

    # Original config is intact (Pattern 4 atomicity invariant).
    assert config_path.read_text(encoding="utf-8") == original_body
    # Temp file was unlinked; no `<config_path>.tmp.*` siblings remain.
    leftover_temps = list(tmp_path.glob("config.yaml.tmp.*"))
    assert leftover_temps == [], f"temp files leaked: {leftover_temps!r}"


# ---------------------------------------------------------------------------
# AC-7 item 10 — record_install_method idempotence.
# ---------------------------------------------------------------------------


def test_record_install_method_idempotence(tmp_path: pathlib.Path) -> None:
    """Calling `record_install_method` twice with the same value produces
    byte-identical content on disk."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text("retry_budget: 5\n", encoding="utf-8")

    record_install_method(InstallMethod("git-clone-symlink"), config_path)
    body_after_first = config_path.read_text(encoding="utf-8")

    record_install_method(InstallMethod("git-clone-symlink"), config_path)
    body_after_second = config_path.read_text(encoding="utf-8")

    assert body_after_first == body_after_second, (
        "second write produced a different body — idempotence violated"
    )
    assert "install_method: git-clone-symlink" in body_after_second


# ---------------------------------------------------------------------------
# AC-7 item 11 — plugin-manifest schema validity.
# ---------------------------------------------------------------------------


def test_plugin_manifest_schema_validity() -> None:
    """`bmad-autopilot/.claude-plugin/plugin.json` parses as JSON, the
    required `name` field is present, and `name` matches the kebab-case
    constraint per Claude Code's docs surface."""
    manifest_path = _INNER_REPO_ROOT / ".claude-plugin" / "plugin.json"
    assert manifest_path.exists(), (
        f"Story 7.2 plugin manifest missing at {manifest_path!s}"
    )

    body = manifest_path.read_text(encoding="utf-8")
    manifest = json.loads(body)

    assert isinstance(manifest, dict), "plugin.json top-level must be a JSON object"
    assert "name" in manifest, "plugin.json missing required `name` field"
    name = manifest["name"]
    assert isinstance(name, str)
    assert PLUGIN_NAME_PATTERN.match(name), (
        f"plugin.json name {name!r} violates kebab-case constraint "
        f"({PLUGIN_NAME_PATTERN.pattern})"
    )
    # Sanity — the name matches FR35's `/plugin install bmad-automation`.
    assert name == "bmad-automation"


# ---------------------------------------------------------------------------
# Smoke test — default path resolution (exercises _inner_repo_root() against
# the real audit doc; guards against parents-depth regressions).
# ---------------------------------------------------------------------------


def test_default_audit_doc_path_resolves_and_parses() -> None:
    """Calling `parse_spike_outcome()` with no arguments (i.e., using the
    module's default path resolution via `_inner_repo_root()`) must succeed
    and return the current Story 7.1 outcome (2) from the real audit doc.

    This test fails if `_inner_repo_root()` resolves to a wrong directory
    (depth off-by-one, wrong install layout, etc.)."""
    from loud_fail_harness.install_path import default_audit_doc_path

    audit_path = default_audit_doc_path()
    assert audit_path.exists(), (
        f"default_audit_doc_path() resolved to {audit_path!s} which does not exist; "
        "check _inner_repo_root() parents depth"
    )

    outcome = parse_spike_outcome()  # no explicit path → uses default
    assert outcome.outcome == 2, (
        f"Expected Story 7.1 outcome 2 from the real audit doc; got outcome {outcome.outcome}"
    )
