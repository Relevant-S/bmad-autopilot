"""Install-path priority + ``install_method`` recording — Story 7.2 substrate module.

## Substrate-component identity

THIS module is a substrate **library** sibling of
:mod:`loud_fail_harness.run_state` / :mod:`loud_fail_harness.specialist_dispatch`
/ :mod:`loud_fail_harness.cost_telemetry` per architecture.md lines 311-315
(harness modules are reusable runtime components per the existing convention
established by Stories 2.3 / 2.6 / 5.1+ / 6.4). It is NOT a sixth substrate
component beyond ADR-003 Consequence 1's enumerated five; the count remains
FIVE.

The module is the FIRST Epic-7 runtime-code introduction (Story 7.1 was
documentation-only). Consumers:

* The orchestrator skill at ``init`` time (Story 7.3+) — calls
  :func:`resolve_install_method` to decide which install path to surface
  to the practitioner; calls :func:`record_install_method` after a
  successful install to persist the decision in
  ``_bmad/automation/config.yaml``.
* Harness CI gates that verify install-method recording correctness —
  composes with the existing module registry without introducing a
  parallel runtime tree.

## Architectural anchors

- **FR35** (PRD line 860) — ``/plugin install bmad-automation`` install
  primitive (consumed when stable per Story 7.1's outcome).
- **FR36** (PRD line 861) — git-clone-symlink fallback install path.
- **FR42** (PRD) — re-runs preserve customization. The user's
  ``_bmad/automation/config.yaml`` may carry hand-edited keys;
  :func:`record_install_method` MUST preserve them via round-trip-safe
  YAML (``ruamel.yaml``) and Pattern 4 atomic-write discipline.
- **Story 7.1 outcome 2** — "Plugin primitive unstable but functional"
  per the verbatim classification text "Claude Code plugin primitive
  available but flagged experimental" from
  ``_bmad-output/planning-artifacts/epics.md`` line 2893. Story 7.2 ships
  git-clone-symlink as the PRIMARY install path; plugin install is
  OPT-IN via ``--use-plugin-experimental`` flag per ``epics.md`` line 2926
  verbatim. The path-priority logic READS the outcome from the
  per-convention row in ``bmad-autopilot/docs/extension-audit.md`` so a
  future re-audit can flip the priority WITHOUT code changes.
- **ADR-003** — substrate-library posture. The harness module surface is
  CI-only at the PROCESS level; the modules INSIDE ``loud_fail_harness/``
  are reusable runtime components per Stories 2.3 / 2.6 / 5.1+.
- **Pattern 4** (architecture.md lines 980-988) — write-temp-then-atomic-
  rename. :func:`record_install_method` writes to ``<config_path>.tmp``
  and ``os.replace``-s into place so a crash mid-write never leaves a
  partial config.
- **Pattern 5** (architecture.md, loud-fail / named invariants) —
  audit-doc drift loud-fails via :class:`InstallPathConfigError` rather
  than silently falling back to a default outcome.
- **Pattern 6** — Python code style; strict typing; ``ruamel.yaml`` for
  round-trip-safe YAML (per the dependency rationale in
  ``pyproject.toml`` `[project.dependencies]``).

## Loud-fail invariants

* ``audit-doc-drift`` — :func:`parse_spike_outcome` raises
  :class:`InstallPathConfigError` if the audit-doc row matches NEITHER of
  the three canonical outcome strings OR matches MULTIPLE.
* ``flag-on-deferred-outcome`` — :func:`resolve_install_method` raises
  :class:`InstallPathConfigError` when ``use_plugin_experimental=True``
  is requested under Story 7.1 outcome 3 (plugin deferred / unavailable).

Both invariants cite Pattern 5: silent fallback to a default outcome (or
silently honoring an inert flag) would mask configuration errors.
"""

from __future__ import annotations

import io
import logging
import os
import pathlib
import re
import secrets
import warnings
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel
from ruamel.yaml import YAML

from .exceptions import ContractViolation

__all__ = [
    "InstallMethod",
    "InstallMethodValue",
    "OUTCOME_TEXT_OUTCOME_1",
    "OUTCOME_TEXT_OUTCOME_2",
    "OUTCOME_TEXT_OUTCOME_3",
    "SpikeOutcome",
    "InstallPathConfigError",
    "default_audit_doc_path",
    "default_config_path",
    "parse_spike_outcome",
    "resolve_install_method",
    "record_install_method",
]

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Verbatim classification-entry texts from `_bmad-output/planning-artifacts/
# epics.md` lines 2892 / 2893 / 2894. The strings are byte-stable per Story
# 7.1 AC-4 (verbatim text discipline) so the parser can byte-match without
# paraphrasing tolerance.
# ---------------------------------------------------------------------------

OUTCOME_TEXT_OUTCOME_1: Literal[
    "Claude Code plugin primitive used as primary install path"
] = "Claude Code plugin primitive used as primary install path"
"""Verbatim classification text for Story 7.1 outcome 1 (plugin stable / primary)."""

OUTCOME_TEXT_OUTCOME_2: Literal[
    "Claude Code plugin primitive available but flagged experimental"
] = "Claude Code plugin primitive available but flagged experimental"
"""Verbatim classification text for Story 7.1 outcome 2 (plugin unstable but functional)."""

OUTCOME_TEXT_OUTCOME_3: Literal[
    "Claude Code plugin primitive deferred"
] = "Claude Code plugin primitive deferred"
"""Verbatim classification text for Story 7.1 outcome 3 (plugin unavailable / deferred)."""

_OUTCOME_TEXT_TO_INT: dict[str, Literal[1, 2, 3]] = {
    OUTCOME_TEXT_OUTCOME_1: 1,
    OUTCOME_TEXT_OUTCOME_2: 2,
    OUTCOME_TEXT_OUTCOME_3: 3,
}


# ---------------------------------------------------------------------------
# Typed Pydantic surface (Pattern 6 — strict typing).
# ---------------------------------------------------------------------------

InstallMethodValue = Literal["plugin", "git-clone-symlink"]
"""The two install-method values bound to ``_bmad/automation/config.yaml``'s
``install_method`` field per ``epics.md`` line 2930 verbatim
(``plugin | git-clone-symlink``)."""


class InstallMethod(RootModel[InstallMethodValue]):
    """Typed wrapper around the install-method literal.

    Wrapped as a Pydantic ``RootModel`` per Story 7.2 Task 1 directive so
    the value can be passed through Pydantic-aware boundaries (envelopes,
    run-state) with the same validation discipline as other typed values
    in the substrate. Construct via ``InstallMethod("plugin")`` or
    ``InstallMethod(root="git-clone-symlink")``; introspect via the
    ``.root`` attribute.
    """

    model_config = ConfigDict(frozen=True)


class SpikeOutcome(BaseModel):
    """Typed Story 7.1 spike-outcome record parsed from the audit doc.

    Carries the integer outcome (1/2/3) AND the verbatim classification
    text the parser matched. The dual surface lets downstream callers
    cite either form without re-parsing.
    """

    model_config = ConfigDict(frozen=True)

    outcome: Literal[1, 2, 3] = Field(
        ..., description="Integer outcome ID (1=plugin primary, 2=experimental, 3=deferred)."
    )
    classification_text: str = Field(
        ...,
        description=(
            "Verbatim classification-entry text matched in the audit doc per "
            "epics.md lines 2892 / 2893 / 2894."
        ),
    )


# ---------------------------------------------------------------------------
# Pattern 5 named-invariant exception.
# ---------------------------------------------------------------------------


class InstallPathConfigError(ContractViolation):
    """Raised on install-path configuration drift or invalid flag combinations.

    Story 7.2 (Pattern 5 — loud-fail / named invariants) — the install-path
    module enforces two structural invariants:

    * **audit-doc-drift** — the per-convention row in
      ``bmad-autopilot/docs/extension-audit.md`` MUST match exactly one of
      the three canonical outcome strings from ``epics.md`` lines 2892 /
      2893 / 2894. No-match OR multiple-match raises this exception so
      drift surfaces loudly rather than silently coercing to a default
      outcome.
    * **flag-on-deferred-outcome** — under Story 7.1 outcome 3 (plugin
      primitive deferred / unavailable), ``use_plugin_experimental=True``
      is structurally inert because the primitive is unavailable. Honoring
      it silently would mask the contradiction; raising surfaces the
      ill-formed request to the orchestrator's slash-command surface.

    Pattern 5 + NFR-O5 (named-invariant diagnostics) require that both
    failure modes surface as contract violations rather than silent
    fallbacks. Inherits from :class:`loud_fail_harness.exceptions.ContractViolation`
    so generic ``except ContractViolation`` at the orchestrator boundary
    catches it alongside the other Pattern-5 invariants.

    Attributes:
        invariant: The named invariant violated (``"audit-doc-drift"`` or
            ``"flag-on-deferred-outcome"``).
        diagnostic: The NFR-O5 named-invariant diagnostic enumerating the
            offending state and a remediation hint pointing at the
            audit-doc row OR the slash-command argument that triggered
            the failure.
    """

    def __init__(self, *, invariant: str, diagnostic: str) -> None:
        self.invariant = invariant
        self.diagnostic = diagnostic
        super().__init__(diagnostic)

    def __str__(self) -> str:
        return f"InstallPathConfigError[{self.invariant}]: {self.diagnostic}"


# ---------------------------------------------------------------------------
# Default-path resolution helpers (file-path-parameterized per AC-1; the
# defaults walk up from the module's own location so the audit-doc location
# is not hardcoded into the module's behavior).
# ---------------------------------------------------------------------------


def _inner_repo_root() -> pathlib.Path:
    """Walk up to the inner-repo root (``bmad-autopilot/``).

    The module lives at
    ``bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/install_path.py``
    so ``parents[4]`` is the inner-repo root. Mirrors the resolution
    pattern used by ``tests/test_marker_taxonomy.py`` and Story 7.2's
    test module.
    """
    return pathlib.Path(__file__).resolve().parents[4]


def default_audit_doc_path() -> pathlib.Path:
    """Resolve the canonical ``docs/extension-audit.md`` location.

    Default for :func:`parse_spike_outcome` and
    :func:`resolve_install_method`. Tests inject a fixture path so the
    audit-doc location is not hardcoded into the module's behavior
    (AC-1's file-path-parameterized requirement).
    """
    return _inner_repo_root() / "docs" / "extension-audit.md"


def default_config_path() -> pathlib.Path:
    """Resolve the canonical ``_bmad/automation/config.yaml`` location.

    Default for :func:`record_install_method`. Tests inject a
    ``tmp_path``-rooted path so the helper does NOT reach into the
    workspace's real config during test runs.
    """
    return _inner_repo_root().parent / "_bmad" / "automation" / "config.yaml"


# ---------------------------------------------------------------------------
# Audit-doc parser (AC-1).
# ---------------------------------------------------------------------------


def parse_spike_outcome(audit_doc_path: pathlib.Path | None = None) -> SpikeOutcome:
    """Parse the Story 7.1 spike outcome from the audit doc.

    Reads ``audit_doc_path`` (default: :func:`default_audit_doc_path`) and
    byte-matches each of the three canonical classification-entry texts
    from ``epics.md`` lines 2892 / 2893 / 2894 against the file body. The
    invariant is exactly ONE match; zero-match OR two-or-more-match raises
    :class:`InstallPathConfigError`.

    Args:
        audit_doc_path: Path to the audit doc. Default resolves to
            ``bmad-autopilot/docs/extension-audit.md`` via
            :func:`default_audit_doc_path`. Tests inject a fixture path.

    Returns:
        :class:`SpikeOutcome` carrying the integer outcome (1/2/3) AND
        the verbatim classification text matched.

    Raises:
        InstallPathConfigError: ``invariant="audit-doc-drift"`` if the
            audit doc matches NEITHER of the three canonical outcome
            strings OR matches MULTIPLE. Pattern 5 — silent fallback to
            a default outcome would mask audit-doc drift.
        FileNotFoundError: ``audit_doc_path`` does not exist (the harness
            module is CI-only so callers always supply a real path; no
            "missing OK" fallback is appropriate).
    """
    path = audit_doc_path if audit_doc_path is not None else default_audit_doc_path()
    try:
        body = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise InstallPathConfigError(
            invariant="audit-doc-unreadable",
            diagnostic=(
                f"audit doc at {path!s} could not be decoded as UTF-8: {exc}. "
                "Ensure the file is saved with UTF-8 encoding before re-running."
            ),
        ) from exc

    matched: list[str] = [text for text in _OUTCOME_TEXT_TO_INT if text in body]

    if len(matched) == 0:
        raise InstallPathConfigError(
            invariant="audit-doc-drift",
            diagnostic=(
                f"audit doc at {path!s} contains NONE of the three canonical "
                "Story 7.1 outcome strings from `_bmad-output/planning-artifacts/"
                "epics.md` lines 2892 / 2893 / 2894 — append the per-convention "
                "row's classification-entry text verbatim before re-running."
            ),
        )
    if len(matched) > 1:
        raise InstallPathConfigError(
            invariant="audit-doc-drift",
            diagnostic=(
                f"audit doc at {path!s} contains MULTIPLE Story 7.1 outcome "
                f"strings ({matched!r}) — exactly one classification entry is "
                "the canonical outcome; resolve the drift in `bmad-autopilot/"
                "docs/extension-audit.md` before re-running."
            ),
        )

    text = matched[0]
    return SpikeOutcome(outcome=_OUTCOME_TEXT_TO_INT[text], classification_text=text)


# ---------------------------------------------------------------------------
# Install-method resolver (AC-2 / AC-3).
# ---------------------------------------------------------------------------


def resolve_install_method(
    use_plugin_experimental: bool = False,
    audit_doc_path: pathlib.Path | None = None,
) -> InstallMethod:
    """Resolve the install method per Story 7.1 outcome + opt-in flag.

    Dispatches per the byte-matched outcome strings (read from the audit
    doc via :func:`parse_spike_outcome`):

    * **outcome 1** (plugin primary) — ``InstallMethod("plugin")``
      regardless of flag (the flag is a no-op when plugin is already
      primary).
    * **outcome 2** (plugin experimental) — ``InstallMethod("git-clone-symlink")``
      by default; ``InstallMethod("plugin")`` with a structured warning
      when ``use_plugin_experimental=True`` (the practitioner explicitly
      opted in to the experimental path per ``epics.md`` line 2926
      verbatim).
    * **outcome 3** (plugin deferred) — ``InstallMethod("git-clone-symlink")``
      by default; raises :class:`InstallPathConfigError` if
      ``use_plugin_experimental=True`` because the primitive is
      unavailable (Pattern 5 — silent fallback would mask the
      contradiction).

    Per-call telemetry — every resolve invocation surfaces in the module
    logger (``loud_fail_harness.install_path``) at INFO level with the
    outcome + the resolved method. This composes with the existing
    Python ``logging`` surface used by sibling modules (e.g.
    :mod:`loud_fail_harness.specialist_dispatch`) WITHOUT introducing a
    new event class — Story 6.4's per-call cost-event log targets
    LLM-specialist dispatches and is structurally orthogonal.

    Args:
        use_plugin_experimental: Practitioner-supplied opt-in flag (the
            ``--use-plugin-experimental`` slash-command flag from
            ``epics.md`` line 2926 verbatim). The orchestrator skill
            (Story 7.3+) plumbs this through from the slash-command
            argument parser.
        audit_doc_path: Path to the audit doc; passed to
            :func:`parse_spike_outcome`.

    Returns:
        :class:`InstallMethod` carrying the resolved value.

    Raises:
        InstallPathConfigError: ``invariant="flag-on-deferred-outcome"``
            if ``use_plugin_experimental=True`` under Story 7.1 outcome 3.
        InstallPathConfigError: ``invariant="audit-doc-drift"`` propagated
            from :func:`parse_spike_outcome` if the audit doc has drifted.
    """
    spike = parse_spike_outcome(audit_doc_path)

    method: InstallMethod
    if spike.outcome == 1:
        method = InstallMethod("plugin")
    elif spike.outcome == 2:
        if use_plugin_experimental:
            warnings.warn(
                (
                    "Plugin install is experimental per Story 7.1 outcome 2 "
                    "(classification text: "
                    f"'{spike.classification_text}'). The "
                    "--use-plugin-experimental flag opted in to the "
                    "experimental install path; promotion to primary "
                    "requires re-audit per the revisit condition in "
                    "`bmad-autopilot/docs/extension-audit.md` § 'Per-convention "
                    "table' (Story 7.1 row)."
                ),
                stacklevel=2,
            )
            method = InstallMethod("plugin")
        else:
            method = InstallMethod("git-clone-symlink")
    else:
        # outcome == 3 (Literal narrowing exhausted)
        if use_plugin_experimental:
            raise InstallPathConfigError(
                invariant="flag-on-deferred-outcome",
                diagnostic=(
                    "Plugin install is deferred per Story 7.1 outcome 3 "
                    f"(classification text: '{spike.classification_text}'); "
                    "the `--use-plugin-experimental` flag has no effect "
                    "because the primitive is unavailable. Either re-audit "
                    "per the per-convention row's revisit conditions OR "
                    "drop the flag and use git-clone-symlink."
                ),
            )
        method = InstallMethod("git-clone-symlink")

    _logger.info(
        "install_path.resolve",
        extra={
            "spike_outcome": spike.outcome,
            "use_plugin_experimental": use_plugin_experimental,
            "resolved_install_method": method.root,
        },
    )
    return method


# ---------------------------------------------------------------------------
# Install-method recording (AC-4) — Pattern 4 atomic write.
# ---------------------------------------------------------------------------


def _atomic_write_text(path: pathlib.Path, body: str) -> None:
    """Pattern 4 atomic write — write to ``<path>.tmp.<pid>.<token>`` and
    ``os.replace`` into ``path``.

    Mirrors the pattern documented in
    :func:`loud_fail_harness.run_state.advance_run_state`:
    ``os.open`` (``O_WRONLY | O_CREAT | O_EXCL``) → write → fsync → close
    → ``os.replace``. The temp file is unlinked on any failure between
    create and replace so the on-disk state is never partial.

    The helper is local to this module (rather than promoted to
    ``_shared.py``) because Story 7.2's scope is bounded; future Epic-7
    consumers may extract a shared helper at the third-caller mark per
    the convention established by ``_shared.py``'s landing in Story 1.5.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(
        f"{path.name}.tmp.{os.getpid()}.{secrets.token_hex(4)}"
    )
    try:
        fd = os.open(temp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(body)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp_path, path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def _yaml_round_trip() -> YAML:
    """Construct a ``ruamel.yaml.YAML`` instance configured for round-trip.

    Round-trip mode preserves comments, key ordering, and quoting style
    so user-edited keys in ``_bmad/automation/config.yaml`` survive
    ``record_install_method`` writes (FR42 — re-runs preserve
    customization).
    """
    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    return yaml


def record_install_method(
    method: InstallMethod,
    config_path: pathlib.Path | None = None,
) -> None:
    """Persist the install method into ``_bmad/automation/config.yaml``.

    Reads the existing config (or starts from an empty mapping if the
    file does not exist), sets the top-level ``install_method`` key,
    and writes atomically via Pattern 4. Round-trip-safe YAML
    (``ruamel.yaml``) preserves any other top-level keys, comments, and
    key ordering — the user's hand-edited customizations survive
    re-installs (FR42).

    Idempotence: writing the same value twice is a no-op on disk content
    (the file mtime may change because the atomic-rename touches it, but
    the rendered YAML body is byte-identical when no other keys
    changed). Writing a different value OVERWRITES — the install module
    is the canonical single-writer of the ``install_method`` key per
    ADR-005's multi-writer-discipline; no other code path writes this
    key.

    Args:
        method: The :class:`InstallMethod` to persist.
        config_path: Path to the user's runtime config. Default resolves
            to ``_bmad/automation/config.yaml`` (relative to the inner
            repo root) via :func:`default_config_path`. Tests inject a
            ``tmp_path``-rooted path.

    Raises:
        OSError: The temp-write or atomic-rename failed at the OS layer
            (e.g., disk full, permission denied). The temp file is
            unlinked before re-raise; the original config (if any) is
            preserved intact per Pattern 4.
    """
    path = config_path if config_path is not None else default_config_path()
    yaml = _yaml_round_trip()

    if path.exists():
        loaded = yaml.load(io.StringIO(path.read_text(encoding="utf-8")))
        # `ruamel.yaml.YAML(typ="rt").load` returns its own `CommentedMap`
        # for round-trip mappings; None means an empty file — start from an
        # empty mapping. Any other top-level type is a malformed config —
        # loud-fail per Pattern 5 rather than crashing with an unclassified
        # TypeError on the subscript assignment below.
        if loaded is None:
            data = yaml.load(io.StringIO("{}\n"))
        elif not hasattr(loaded, "__setitem__"):
            raise InstallPathConfigError(
                invariant="malformed-config",
                diagnostic=(
                    f"config at {path!s} has a non-mapping top-level YAML type "
                    f"({type(loaded).__name__!r}); expected a YAML mapping. "
                    "Restore or delete the file before re-running."
                ),
            )
        else:
            data = loaded
    else:
        data = yaml.load(io.StringIO("{}\n"))

    data["install_method"] = method.root

    buffer = io.StringIO()
    yaml.dump(data, buffer)
    body = buffer.getvalue()

    _atomic_write_text(path, body)

    _logger.info(
        "install_path.record",
        extra={
            "config_path": str(path),
            "install_method": method.root,
        },
    )


# ---------------------------------------------------------------------------
# Plugin-manifest constraints (AC-5) — exposed for cross-module checks.
# ---------------------------------------------------------------------------

PLUGIN_NAME_PATTERN: re.Pattern[str] = re.compile(r"^[a-z][a-z0-9-]*$")
"""Kebab-case constraint for the plugin manifest's ``name`` field per the
Claude Code docs surface at ``https://code.claude.com/docs/en/plugins-reference``
(``"Unique identifier (kebab-case, no spaces)"``). Used by
``tests/test_install_path.py`` to validate the shipped manifest's ``name``
field round-trips against the canonical regex."""
