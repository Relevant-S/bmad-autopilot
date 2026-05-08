"""Non-destructive ``init`` guard + additive-merge + audit-log — Story 7.6 substrate module.

## Substrate-component identity

THIS module is a substrate **library** sibling of
:mod:`loud_fail_harness.install_path` (Story 7.2),
:mod:`loud_fail_harness.init_preconditions` (Story 7.3),
:mod:`loud_fail_harness.sample_story_scaffold` (Story 7.4), and
:mod:`loud_fail_harness.config_qa_runbook_stub` (Story 7.5). It is NOT a
sixth substrate component beyond ADR-003 Consequence 1's enumerated
five; the count remains FIVE.

The module is the SIXTH Epic-7 runtime-code introduction (after Stories
7.2, 7.3, 7.4, 7.5; Story 7.1 was documentation-only). Consumers:

* The orchestrator skill at ``init`` time (Story 7.6 thickening of
  ``skills/bmad-automation/steps/init.md``) — calls
  :func:`evaluate_non_destructive_guard` BEFORE the scaffolders, and
  routes on ``GuardOutcome.action`` to either Story 7.4's + 7.5's
  scaffolders (``proceed-fresh`` / ``overwrite-confirmed``) OR the
  additive-merge layer here (``preserve-merge``) OR a halt with
  ``init-would-destroy-existing-artifact`` marker (``halt-would-destroy``).

## Architectural anchors

- **FR41** (PRD line 866) — ``init`` is non-destructive on existing
  BMAD projects; never overwrites user-owned content in
  ``_bmad-output/`` or story docs.
- **FR42** (PRD line 867) — ``init`` re-runs preserve user
  configuration; upgrades do not lose customizations to
  ``config.yaml`` or ``qa-runbook.yaml``.
- **Story 1.4 v1 marker taxonomy** — ``init-would-destroy-existing-artifact``
  is the canonical halt marker; this module CONSUMES the existing
  taxonomy entry AS-IS (NO new marker classes).
- **Story 1.11 atomic-vs-aggregated principle** — no new umbrella
  marker classes (``init-merge-failed``, ``init-overwrite-without-confirmation``
  etc.); the existing class covers all halt routes via the freeform
  context payload.
- **Story 4.12 absence-of-marker doctrine** — the override-confirmed
  path emits NO marker; the audit trail comes from a structured log
  entry at ``_bmad-output/init-history/{timestamp}.log`` rather than
  a marker class. The deliberate-decision audit row in
  ``docs/extension-audit.md`` mirrors Story 4.12's ``masked_selectors``
  row shape.
- **Story 7.2 ruamel.yaml round-trip pattern** — the text-level
  append in :func:`_additively_merge` preserves existing content
  byte-for-byte without ruamel round-trip; ``ruamel.yaml`` is still
  a declared dep (used by :mod:`loud_fail_harness.install_path`).
- **Story 7.4 ``is_absolute`` field validator precedent** — mirrored
  on ``GuardRequest.project_root``.
- **Story 7.5 path-resolver consumption** — ``resolve_config_path``,
  ``resolve_qa_runbook_path``, ``load_config_template``,
  ``load_qa_runbook_template`` are imported AS-IS.
- **Pattern 4** atomic-write — temp-file + ``os.replace``; mirrored
  byte-for-byte from :func:`loud_fail_harness.install_path._atomic_write_text`
  (Story 7.6 is the SECOND caller; Story 7.2's "third-caller" promotion
  threshold per ``install_path.py:447-460`` keeps the helper local until
  the third caller arrives).
- **Pattern 5** loud-fail / named invariants — :class:`GuardConfigCorrupted`
  surfaces malformed existing YAML with a remediation hint mirroring
  :class:`loud_fail_harness.install_path.InstallPathConfigError`.
- **Pattern 6** Python code style — strict typing, frozen Pydantic
  models, caller-injected ``project_root`` so tests use ``tmp_path``.

## The four ``GuardOutcome.action`` branches

* ``proceed-fresh`` — no existing user-owned files; orchestrator runs
  Story 7.4's + 7.5's scaffolders.
* ``preserve-merge`` — existing files present AND override flag absent
  AND merge probes succeed; orchestrator calls
  :func:`additively_merge_config` + :func:`additively_merge_qa_runbook`
  AND skips sample-story regeneration (existing file preserved
  byte-for-byte).
* ``overwrite-confirmed`` — ``override_confirmed=True`` AND
  ``secondary_confirmed=True``; structured audit-log entry written;
  orchestrator runs the scaffolders verbatim. NO marker.
* ``halt-would-destroy`` — secondary confirmation missing OR existing
  config is malformed YAML; ``init-would-destroy-existing-artifact``
  marker emitted exactly once.
"""

from __future__ import annotations

import logging
import os
import pathlib
import re
import secrets
from datetime import datetime, timezone
from typing import Any, Literal

import yaml as _pyyaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .config_qa_runbook_stub import (
    load_config_template,
    load_qa_runbook_template,
    resolve_config_path,
    resolve_qa_runbook_path,
)
from .exceptions import ContractViolation
from .marker_wiring import record_marker_with_context
from .run_state import RunState
from .sample_story_scaffold import resolve_target_path as resolve_sample_story_path
from .specialist_dispatch import MarkerClassRegistry

__all__ = [
    "AUDIT_LOG_SUBDIR",
    "AUDIT_LOG_FILENAME_PATTERN",
    "INIT_WOULD_DESTROY_MARKER_CLASS",
    "GuardConfigCorrupted",
    "GuardOutcome",
    "GuardRequest",
    "MergeResult",
    "additively_merge_config",
    "additively_merge_qa_runbook",
    "detect_existing_user_owned_artifacts",
    "evaluate_non_destructive_guard",
    "write_init_history_entry",
]

_logger = logging.getLogger(__name__)

#: The canonical audit-log directory, relative to ``project_root``.
AUDIT_LOG_SUBDIR: tuple[str, str] = ("_bmad-output", "init-history")

#: Audit-log filename shape: ``{YYYYMMDDTHHMMSSZ}.log`` per Story 4.12's
#: ``allocate_run_id`` convention at ``qa_evidence_persistence.py:226-255``.
AUDIT_LOG_FILENAME_PATTERN: re.Pattern[str] = re.compile(r"^\d{8}T\d{6}Z\.log$")

#: The Story 1.4 v1 marker class consumed AS-IS by this module on the
#: halt path. NO new marker classes introduced (per Story 1.11
#: atomic-vs-aggregated principle).
INIT_WOULD_DESTROY_MARKER_CLASS: Literal[
    "init-would-destroy-existing-artifact"
] = "init-would-destroy-existing-artifact"

_HaltRoute = Literal[
    "secondary-confirmation-missing",
    "merge-failed",
]

_GuardAction = Literal[
    "proceed-fresh",
    "preserve-merge",
    "overwrite-confirmed",
    "halt-would-destroy",
]


# --------------------------------------------------------------------------- #
# Typed Pydantic models (Pattern 6 — explicit, frozen, named).                 #
# --------------------------------------------------------------------------- #


class GuardRequest(BaseModel):
    """Typed input to :func:`evaluate_non_destructive_guard`.

    Pattern 6 — frozen so callers cannot mutate the request mid-evaluation.
    The four boolean flags are mutually orthogonal and each carries an
    explicit-narrow contract; an enum (e.g., ``Mode.RE_RUN``) would
    conflate ``override_confirmed`` with ``secondary_confirmed`` and lose
    the structural ability to express the "override-without-secondary"
    halt route.

    Attributes:
        project_root: The practitioner's BMAD project root. The guard
            inspects three canonical scaffold-target paths under this
            root via Stories 7.4's + 7.5's path resolvers. REQUIRED;
            no default. ``is_absolute`` is enforced at validation time
            mirroring ``SampleScaffoldRequest._project_root_must_be_absolute``
            at ``sample_story_scaffold.py:202-211``.
        override_confirmed: Mirrors the parsed boolean of the
            ``--overwrite-confirmed`` flag. Default ``False``. When
            ``True`` AND ``secondary_confirmed`` is ``True``, the guard
            bypasses non-destructive checks and writes a structured
            audit-log entry.
        secondary_confirmed: Mirrors the parsed boolean of the ``--yes``
            flag (or completion of the interactive secondary
            confirmation prompt at the orchestrator-skill thickening
            layer). Default ``False``. Independent of
            ``override_confirmed`` — the practitioner must pass BOTH
            for an explicit override per ``epics.md`` lines 3061-3064.
        no_sample_story: Mirrors the parsed boolean of the
            ``--no-sample-story`` flag. Default ``False``. Orthogonal
            to override; preserved per Story 7.4's opt-out flow. The
            guard does NOT consume this field directly; it is
            forwarded by the orchestrator skill to Story 7.4's
            scaffolder via ``SampleScaffoldRequest.opt_out``.
    """

    model_config = ConfigDict(frozen=True)

    project_root: pathlib.Path = Field(
        ...,
        description=(
            "The practitioner's BMAD project root; the guard inspects "
            "three canonical scaffold-target paths under this root."
        ),
    )
    override_confirmed: bool = Field(
        default=False,
        description=(
            "Mirrors `--overwrite-confirmed`; True bypasses the guard "
            "(when paired with `secondary_confirmed=True`)."
        ),
    )
    secondary_confirmed: bool = Field(
        default=False,
        description=(
            "Mirrors `--yes`; required AS PAIR with `override_confirmed` "
            "to take the override path (`epics.md` lines 3061-3064)."
        ),
    )
    no_sample_story: bool = Field(
        default=False,
        description=(
            "Mirrors `--no-sample-story`; orthogonal to override; "
            "forwarded by the orchestrator skill to Story 7.4's "
            "`SampleScaffoldRequest.opt_out`."
        ),
    )

    @field_validator("project_root")
    @classmethod
    def _project_root_must_be_absolute(cls, v: pathlib.Path) -> pathlib.Path:
        if not v.is_absolute():
            raise ValueError(
                f"project_root must be an absolute path; got {v!r}. "
                "Pass pathlib.Path.cwd() or a CLI-resolved absolute path."
            )
        return v


class GuardOutcome(BaseModel):
    """Typed return of :func:`evaluate_non_destructive_guard`.

    Pattern 6 — frozen so the orchestrator skill cannot mutate the
    outcome between read and route.

    Attributes:
        action: One of the four canonical actions. The orchestrator
            skill at ``init.md`` thickening time switches on this
            field to route to scaffolders / merge / halt.
        existing_files: The detected user-owned file paths under
            ``project_root`` that triggered the route. Empty tuple on
            ``proceed-fresh``.
        audit_log_path: Set when ``action="overwrite-confirmed"``;
            ``None`` otherwise. The path is the resolved target of the
            structured-log file written by
            :func:`write_init_history_entry`.
        diagnostic: Set when ``action="halt-would-destroy"``; carries
            the verbatim three-options enumeration text per AC-4
            (``epics.md`` line 3046).
        notes: Always populated; one-line human-readable summary
            suitable for ``init``'s output line.
    """

    model_config = ConfigDict(frozen=True)

    action: _GuardAction
    existing_files: tuple[pathlib.Path, ...]
    audit_log_path: pathlib.Path | None = None
    diagnostic: str | None = None
    notes: str


class MergeResult(BaseModel):
    """Typed return of :func:`additively_merge_config` /
    :func:`additively_merge_qa_runbook`.

    Pattern 6 — frozen.

    Attributes:
        target_path: The resolved on-disk target.
        action: ``"merged"`` if at least one canonical key was added;
            ``"no-op"`` if every canonical key is already present
            (the on-disk file is byte-identical post-call).
        existing_keys_preserved: The count of top-level keys in the
            existing on-disk mapping that were preserved unchanged.
        new_keys_added: The count of canonical-defaults keys appended
            because they were missing from the existing mapping.
        bytes_written: ``int`` when the file was written;
            ``None`` on ``no-op`` (skip-write to minimize mtime churn).
    """

    model_config = ConfigDict(frozen=True)

    target_path: pathlib.Path
    action: Literal["merged", "no-op"]
    existing_keys_preserved: int
    new_keys_added: int
    bytes_written: int | None = None


# --------------------------------------------------------------------------- #
# Loud-fail invariant for malformed existing YAML.                             #
# --------------------------------------------------------------------------- #


class GuardConfigCorrupted(ContractViolation):
    """Raised when an existing user-owned YAML file is structurally malformed.

    Mirrors the diagnostic shape of
    :class:`loud_fail_harness.install_path.InstallPathConfigError`:
    the loud-fail surface enumerates the offending path and a
    remediation hint pointing at the practitioner's recovery options.

    Attributes:
        path: The resolved on-disk path of the malformed file.
        diagnostic: NFR-O5 named-invariant diagnostic naming the file
            and the remediation ("Restore or delete the file before
            re-running").
    """

    def __init__(self, *, path: pathlib.Path, diagnostic: str) -> None:
        self.path = path
        self.diagnostic = diagnostic
        super().__init__(diagnostic)

    def __str__(self) -> str:
        return f"GuardConfigCorrupted[{self.path}]: {self.diagnostic}"


# --------------------------------------------------------------------------- #
# Private helpers (Pattern 4 + Story 7.2 mirror; ruamel.yaml round-trip).      #
# --------------------------------------------------------------------------- #


def _atomic_write_text(path: pathlib.Path, body: str) -> None:
    """Pattern 4 atomic write — temp-file + ``os.replace``.

    Mirrors :func:`loud_fail_harness.install_path._atomic_write_text`
    byte-for-byte. Story 7.6 is the SECOND caller of this pattern;
    Story 7.2's docstring at ``install_path.py:447-460`` documents a
    "third-caller" promotion threshold to ``_shared.py``. The mirror
    is the dev's-call here per Story 2.12 precedent (preferring
    duplication over a one-caller-too-early extraction).
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



def _utc_timestamp(now: datetime | None = None) -> str:
    """Return a 16-character ``YYYYMMDDTHHMMSSZ`` UTC stamp.

    Format pin matches Story 4.12's
    :func:`loud_fail_harness.qa_evidence_persistence.allocate_run_id` —
    drift-prevention: same stamp shape across all ``_bmad-output/``
    audit/evidence surfaces.
    """
    instant = now if now is not None else datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ValueError(
            "now must be timezone-aware; got a naive datetime. "
            "Use datetime.now(timezone.utc) or pass an aware datetime."
        )
    return instant.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _safe_load_top_level_mapping(
    path: pathlib.Path, *, raw: str
) -> dict[str, Any] | None:
    """Parse ``raw`` as YAML and return the top-level mapping.

    Returns ``None`` when the YAML body is empty / all-comments; raises
    :class:`GuardConfigCorrupted` if the YAML body has a non-mapping
    top-level type (e.g., a list or scalar) or fails to parse at all
    (per Pattern 5 — the existing on-disk file is malformed and cannot
    be safely merged).
    """
    try:
        loaded = _pyyaml.safe_load(raw)
    except _pyyaml.YAMLError as exc:
        raise GuardConfigCorrupted(
            path=path,
            diagnostic=(
                f"Existing YAML at {path!s} could not be parsed ({exc}). "
                "Restore or delete the file before re-running "
                "`/bmad-automation init`."
            ),
        ) from exc
    if loaded is None:
        return None
    if not isinstance(loaded, dict):
        raise GuardConfigCorrupted(
            path=path,
            diagnostic=(
                f"Existing YAML at {path!s} has a non-mapping top-level type "
                f"({type(loaded).__name__!r}); expected a YAML mapping. "
                "Restore or delete the file before re-running "
                "`/bmad-automation init`."
            ),
        )
    return loaded


def _extract_canonical_section(canonical_text: str, key: str) -> str:
    """Return the canonical-template section text for ``key``.

    The "section" is the preceding comment block (walking up from the
    key line until a blank line or the start of file) PLUS the key line
    itself PLUS any indented continuation lines that form the value.

    Used by :func:`additively_merge_config` /
    :func:`additively_merge_qa_runbook` to APPEND missing canonical
    keys to the user's existing on-disk file with their canonical
    comment-block + value preserved verbatim.

    Args:
        canonical_text: The full canonical-template text.
        key: The top-level key whose section to extract.

    Returns:
        The section text including a trailing newline. Empty string if
        the key is not found at column 0 (defensive — should never
        happen in practice since the caller pre-parses the canonical
        text and only requests known keys).
    """
    lines = canonical_text.splitlines(keepends=True)
    # Locate the key line at column 0 with shape ``<key>:`` or ``<key>: ...``.
    key_pattern = re.compile(rf"^{re.escape(key)}\s*:")
    key_idx: int | None = None
    for i, line in enumerate(lines):
        if key_pattern.match(line):
            key_idx = i
            break
    if key_idx is None:
        return ""

    # Walk backward to capture the preceding comment block.
    start = key_idx
    while start > 0:
        prev = lines[start - 1]
        if not prev.strip():
            # Blank line — stop; do NOT include the blank itself in the section.
            break
        if prev.startswith("#"):
            start -= 1
            continue
        # Non-comment, non-blank, non-key line — stop (defensive).
        break

    # Walk forward to capture indented continuation lines (the value's body).
    end = key_idx + 1
    while end < len(lines):
        nxt = lines[end]
        if not nxt.strip():
            # Blank line — stop; section ends here.
            break
        if nxt.startswith((" ", "\t")):
            # Indented continuation — part of the value.
            end += 1
            continue
        # Another top-level key OR a top-level comment — stop.
        break

    return "".join(lines[start:end])


def _ensure_trailing_newline(text: str) -> str:
    """Return ``text`` with at least one trailing newline (ensures non-empty terminator)."""
    return text if text.endswith("\n") else text + "\n"


# --------------------------------------------------------------------------- #
# AC-1 — Existence detection across canonical scaffold targets.                #
# --------------------------------------------------------------------------- #


def detect_existing_user_owned_artifacts(
    project_root: pathlib.Path,
) -> tuple[pathlib.Path, ...]:
    """Return the resolved paths of user-owned scaffold-targets that exist.

    Inspects the THREE canonical scaffold-target paths via the public
    path-resolvers from sibling stories — NO new path constants are
    declared in this module (drift-prevention; Story 7.6 reads paths
    from Stories 7.4 + 7.5 substrate, not from local copies):

    1. :func:`loud_fail_harness.sample_story_scaffold.resolve_target_path`
       → ``<project_root>/_bmad-output/implementation-artifacts/sample-auto-001.md``
    2. :func:`loud_fail_harness.config_qa_runbook_stub.resolve_config_path`
       → ``<project_root>/_bmad/automation/config.yaml``
    3. :func:`loud_fail_harness.config_qa_runbook_stub.resolve_qa_runbook_path`
       → ``<project_root>/_bmad/automation/qa-runbook.yaml``

    For each resolved path, ``path.is_file()`` is checked (NOT
    ``path.exists()`` — a directory at the same path is structurally a
    different problem; the guard's halt path is correctness-coupled to
    "user-owned regular file would be overwritten").

    Args:
        project_root: The practitioner's BMAD project root.

    Returns:
        A ``tuple[pathlib.Path, ...]`` containing ONLY paths where
        ``is_file()`` is True. Empty tuple on a fresh project; one or
        more entries on re-run. Order is deterministic: sample-story
        FIRST, config SECOND, qa-runbook THIRD — matches the order
        ``init`` would write them per the orchestrator-skill thickening.

    Side effects:
        NONE — no filesystem writes, no ``mkdir``, no logging. The
        function is byte-deterministic across repeated calls with the
        same ``project_root``.
    """
    candidates: tuple[pathlib.Path, ...] = (
        resolve_sample_story_path(project_root),
        resolve_config_path(project_root),
        resolve_qa_runbook_path(project_root),
    )
    return tuple(p for p in candidates if p.is_file())


# --------------------------------------------------------------------------- #
# AC-2 — Additive-merge layer (config + qa-runbook).                           #
# --------------------------------------------------------------------------- #


def _additively_merge(
    *,
    target_path: pathlib.Path,
    canonical_text: str,
) -> MergeResult:
    """Shared body of :func:`additively_merge_config` /
    :func:`additively_merge_qa_runbook`.

    Implements the AC-2 contract: load canonical defaults; load existing
    on-disk content; for every top-level canonical key NOT in existing,
    APPEND that key's comment-block + value verbatim from the canonical
    template; for every key present in BOTH, leave the existing value +
    comments + position UNCHANGED; for every key in existing NOT in
    canonical (user customizations), preserve unchanged.

    Atomic-writes on merge; skip-writes on no-op (minimizes mtime churn).
    """
    canonical_keys = _canonical_top_level_keys(canonical_text)

    if not target_path.is_file():
        # The guard is invoked AFTER `detect_existing_user_owned_artifacts`
        # confirms the file is present; this branch is defensive only.
        raise GuardConfigCorrupted(
            path=target_path,
            diagnostic=(
                f"Existing file at {target_path!s} disappeared between "
                "detection and merge. Re-run `/bmad-automation init`."
            ),
        )

    existing_raw = target_path.read_text(encoding="utf-8")
    existing_mapping = _safe_load_top_level_mapping(target_path, raw=existing_raw)
    existing_keys: tuple[str, ...] = (
        tuple(existing_mapping.keys()) if existing_mapping is not None else ()
    )

    if not canonical_keys:
        # The qa-runbook canonical template is all-commented-out
        # (parses to None); there are no canonical defaults to add.
        # Per AC-2: return no-op; existing file is unchanged.
        return MergeResult(
            target_path=target_path,
            action="no-op",
            existing_keys_preserved=len(existing_keys),
            new_keys_added=0,
            bytes_written=None,
        )

    existing_keyset = set(existing_keys)
    missing_keys = tuple(k for k in canonical_keys if k not in existing_keyset)

    if not missing_keys:
        return MergeResult(
            target_path=target_path,
            action="no-op",
            existing_keys_preserved=len(existing_keys),
            new_keys_added=0,
            bytes_written=None,
        )

    # Append missing canonical sections at the end of the existing file.
    # The text-level append preserves user content BYTE-FOR-BYTE (no
    # ruamel-round-trip risk to existing comments / quoting / order).
    sections: list[str] = []
    for key in missing_keys:
        section = _extract_canonical_section(canonical_text, key)
        if not section:
            # Defensive: the canonical text was scanned for ``<key>:`` and
            # `_canonical_top_level_keys` returned this key, so the section
            # must exist; this branch is unreachable in practice.
            continue
        sections.append(_ensure_trailing_newline(section))

    merged_text = _ensure_trailing_newline(existing_raw)
    # Insert one blank line between the existing content and the first
    # appended section so the appended block is visually separated.
    merged_text = merged_text + "\n" + "\n".join(sections)
    merged_text = _ensure_trailing_newline(merged_text)

    _atomic_write_text(target_path, merged_text)

    return MergeResult(
        target_path=target_path,
        action="merged",
        existing_keys_preserved=len(existing_keys),
        new_keys_added=len(missing_keys),
        bytes_written=len(merged_text.encode("utf-8")),
    )


def _canonical_top_level_keys(canonical_text: str) -> tuple[str, ...]:
    """Return the top-level keys of ``canonical_text`` in source order.

    Returns an empty tuple when the canonical body parses to None
    (the qa-runbook all-commented-out case).
    """
    parsed = _pyyaml.safe_load(canonical_text)
    if parsed is None:
        return ()
    if not isinstance(parsed, dict):
        # Canonical templates are part of the Automator's own packaged
        # resources; a non-mapping canonical is a build-time bug and
        # should surface loudly rather than coerce to ().
        raise RuntimeError(
            "canonical template parsed to a non-mapping top-level type "
            f"({type(parsed).__name__!r}); expected a YAML mapping. "
            "This is a build-time defect in the harness package."
        )
    return tuple(parsed.keys())


def additively_merge_config(project_root: pathlib.Path) -> MergeResult:
    """Additively merge the canonical config defaults INTO the existing on-disk file.

    Per AC-2: every top-level canonical-defaults key NOT in the
    existing file is APPENDED with its preceding comment block + value
    verbatim; every key present in BOTH is left unchanged; every key
    present in EXISTING but NOT canonical (user customizations) is
    preserved.

    Args:
        project_root: The practitioner's BMAD project root.

    Returns:
        A :class:`MergeResult`.

    Raises:
        GuardConfigCorrupted: The existing on-disk YAML is malformed
            (non-mapping top-level OR YAML parse error).
        OSError: The atomic-write failed at the OS layer.
    """
    target_path = resolve_config_path(project_root)
    canonical_text = load_config_template()
    return _additively_merge(target_path=target_path, canonical_text=canonical_text)


def additively_merge_qa_runbook(project_root: pathlib.Path) -> MergeResult:
    """Additively merge the canonical qa-runbook defaults INTO the existing on-disk file.

    Same shape as :func:`additively_merge_config`. Handles the
    canonical template's all-commented-out posture: when the canonical
    template parses to ``None``, the function returns
    ``MergeResult(action="no-op", new_keys_added=0)`` — there are no
    canonical-defaults keys to add since they're all opt-in
    commented-out (per Story 7.5's qa-runbook template shape).

    Args:
        project_root: The practitioner's BMAD project root.

    Returns:
        A :class:`MergeResult`.

    Raises:
        GuardConfigCorrupted: The existing on-disk YAML is malformed.
        OSError: The atomic-write failed at the OS layer.
    """
    target_path = resolve_qa_runbook_path(project_root)
    canonical_text = load_qa_runbook_template()
    return _additively_merge(target_path=target_path, canonical_text=canonical_text)


# --------------------------------------------------------------------------- #
# AC-3 — Structured audit-log entry.                                           #
# --------------------------------------------------------------------------- #


def write_init_history_entry(
    project_root: pathlib.Path,
    *,
    action: Literal["overwrite-confirmed"],
    files_touched: tuple[pathlib.Path, ...],
    timestamp: str | None = None,
) -> pathlib.Path:
    """Write a structured audit-log entry at ``_bmad-output/init-history/{timestamp}.log``.

    The entry's content carries (per AC-3):

    * ``timestamp`` — ISO-8601 form for human readability
    * ``action`` — the matched ``GuardOutcome.action``
    * ``files_overwritten`` — the resolved paths from
      ``existing_files`` (rendered as strings for YAML clarity)
    * ``practitioner_intent`` — verbatim "explicit override
      (--overwrite-confirmed --yes)"
    * ``loud_fail_marker_emitted: false`` — the structural
      absence-witness; future maintainers reading the audit log
      see the deliberate-decision audit entry's referent embedded
      in the data, not as separate prose
    * ``rationale_pointer`` — references ``docs/extension-audit.md``
      so a maintainer can grep from the log to the doctrine

    Args:
        project_root: The practitioner's BMAD project root.
        action: The :class:`GuardOutcome` action that triggered the
            audit-log write. Currently only ``overwrite-confirmed``
            writes a log entry; ``preserve-merge`` is reserved for
            future expansion (the parameter is typed for symmetry).
        files_touched: The resolved paths of files affected by the
            action.
        timestamp: Optional injected stamp (Pattern 6) for test
            determinism. ``None`` → :func:`_utc_timestamp` resolves
            the current UTC instant.

    Returns:
        The resolved audit-log file path.

    Raises:
        OSError: The atomic-write failed at the OS layer.
        PermissionError: Subclass of ``OSError`` raised when the
            audit-log directory cannot be written. Propagates
            UNCHANGED per Pattern 5.
    """
    stamp = timestamp if timestamp is not None else _utc_timestamp()
    target_dir = project_root
    for segment in AUDIT_LOG_SUBDIR:
        target_dir = target_dir / segment
    target_path = target_dir / f"{stamp}.log"

    # ISO-8601 form of the same instant for the audit-log body. Prefer
    # parsing the compact stamp back to a datetime so the body's
    # human-readable timestamp is byte-deterministic against the
    # filename when callers inject ``timestamp=`` (per AC-7 case 14).
    iso_form = (
        datetime.strptime(stamp, "%Y%m%dT%H%M%SZ")
        .replace(tzinfo=timezone.utc)
        .isoformat()
    )

    body_payload: dict[str, Any] = {
        "timestamp": iso_form,
        "action": action,
        "files_overwritten": [str(p) for p in files_touched],
        "practitioner_intent": "explicit override (--overwrite-confirmed --yes)",
        "loud_fail_marker_emitted": False,
        "rationale_pointer": (
            "see docs/extension-audit.md absence-of-marker-on-intentional-override row"
        ),
    }
    body = _pyyaml.safe_dump(body_payload, sort_keys=False)
    _atomic_write_text(target_path, body)
    return target_path


# --------------------------------------------------------------------------- #
# AC-3 + AC-4 — The composite guard evaluation.                                #
# --------------------------------------------------------------------------- #


def _build_halt_diagnostic(
    *,
    existing_files: tuple[pathlib.Path, ...],
    halt_route: _HaltRoute,
    extra_hint: str | None = None,
) -> str:
    """Render the halt diagnostic per AC-4 — the three practitioner options."""
    files_block = "\n".join(f"  - {p!s}" for p in existing_files) or "  - (none)"
    backup_cmds = (
        "  mv _bmad/automation/config.yaml _bmad/automation/config.yaml.bak\n"
        "  mv _bmad/automation/qa-runbook.yaml _bmad/automation/qa-runbook.yaml.bak\n"
        "  mv _bmad-output/implementation-artifacts/sample-auto-001.md "
        "_bmad-output/implementation-artifacts/sample-auto-001.md.bak"
    )
    diagnostic = (
        "init-would-destroy-existing-artifact: existing user-owned content "
        "detected.\n"
        f"halt_route: {halt_route}\n"
        "Existing files:\n"
        f"{files_block}\n"
        "\n"
        "Practitioner options (FR41 + FR42; per epics.md line 3046):\n"
        "  1. Back up: move the existing files out of the way:\n"
        f"{backup_cmds}\n"
        "     then re-run `/bmad-automation init`.\n"
        "  2. Merge: re-run `/bmad-automation init` without "
        "`--overwrite-confirmed` —\n"
        "     the guard's default behavior is non-destructive: existing "
        "config + qa-runbook\n"
        "     are additively merged (your customizations preserved); the "
        "existing\n"
        "     sample story is preserved as-is.\n"
        "  3. Explicit override: re-run "
        "`/bmad-automation init --overwrite-confirmed --yes` —\n"
        "     destruction is recorded in "
        "`_bmad-output/init-history/{timestamp}.log`."
    )
    if extra_hint:
        diagnostic = f"{diagnostic}\n\n{extra_hint}"
    return diagnostic


def _emit_marker(
    *,
    run_state: RunState | None,
    marker_registry: MarkerClassRegistry | None,
    existing_files: tuple[pathlib.Path, ...],
    halt_route: _HaltRoute,
    note: str,
) -> RunState | None:
    """Emit the ``init-would-destroy-existing-artifact`` marker exactly once.

    Mirrors the null-guard pattern at
    :func:`loud_fail_harness.init_preconditions._dispatch_total_block`
    lines 557-578: the recorder is invoked ONLY when both ``run_state``
    AND ``marker_registry`` are non-None; otherwise the function
    returns ``run_state`` unchanged (which is ``None`` in the
    test-without-runtime case).
    """
    if run_state is None or marker_registry is None:
        return run_state
    context: dict[str, Any] = {
        "halt_route": halt_route,
        "existing_files": [str(p) for p in existing_files],
        "note": note,
    }
    return record_marker_with_context(
        run_state=run_state,
        marker_class=INIT_WOULD_DESTROY_MARKER_CLASS,
        sub_classification=None,
        context=context,
        marker_registry=marker_registry,
    )


def _probe_merge_safety(
    project_root: pathlib.Path,
    existing_files: tuple[pathlib.Path, ...],
) -> pathlib.Path | None:
    """Dry-load the existing config / qa-runbook to surface malformed YAML.

    Returns the FIRST malformed file's path on failure; ``None`` on
    full merge-safety. The function does NOT mutate the on-disk state;
    it parses the existing content with :func:`_safe_load_top_level_mapping`
    which raises :class:`GuardConfigCorrupted`. We swallow the
    exception here and return the path so the caller can route to a
    halt with ``halt_route="merge-failed"``.
    """
    config_target = resolve_config_path(project_root)
    qa_runbook_target = resolve_qa_runbook_path(project_root)
    for target in (config_target, qa_runbook_target):
        if target not in existing_files:
            continue
        try:
            raw = target.read_text(encoding="utf-8")
            _safe_load_top_level_mapping(target, raw=raw)
        except GuardConfigCorrupted:
            return target
    return None


def evaluate_non_destructive_guard(
    request: GuardRequest,
    *,
    run_state: RunState | None = None,
    marker_registry: MarkerClassRegistry | None = None,
) -> tuple[GuardOutcome, RunState | None]:
    """Evaluate the non-destructive-guard contract for ``init``.

    The composite decision function. Returns a :class:`GuardOutcome`
    describing the action the orchestrator skill should take, plus the
    (possibly-updated) :class:`RunState` carrying the marker emission
    on the halt path.

    The four branches:

    1. ``existing_files == ()`` → ``proceed-fresh``.
    2. ``request.override_confirmed`` AND ``request.secondary_confirmed``
       → ``overwrite-confirmed``; structured audit-log entry written;
       NO marker.
    3. ``request.override_confirmed`` AND NOT ``request.secondary_confirmed``
       → ``halt-would-destroy`` (route: ``secondary-confirmation-missing``);
       marker emitted.
    4. Default re-run path (no override) → probe merge safety:
       - On malformed existing YAML: ``halt-would-destroy`` (route:
         ``merge-failed``); marker emitted.
       - Otherwise: ``preserve-merge``; NO marker.

    Args:
        request: The typed input.
        run_state: Optional runtime ``RunState``. When provided AND
            ``marker_registry`` is also provided, the halt path emits
            the ``init-would-destroy-existing-artifact`` marker
            EXACTLY ONCE per evaluation. When ``None`` (e.g., test
            exercises the function without a runtime), no marker is
            emitted and the second tuple-element is ``None``.
        marker_registry: Optional marker registry. See ``run_state``.

    Returns:
        A tuple ``(GuardOutcome, RunState | None)``.
    """
    project_root = request.project_root
    existing_files = detect_existing_user_owned_artifacts(project_root)

    # Branch 1 — fresh project.
    if not existing_files:
        return (
            GuardOutcome(
                action="proceed-fresh",
                existing_files=(),
                audit_log_path=None,
                diagnostic=None,
                notes=(
                    "No existing user-owned content detected. `init` will "
                    "scaffold the canonical stubs."
                ),
            ),
            run_state,
        )

    # Branch 2 — full explicit override.
    if request.override_confirmed and request.secondary_confirmed:
        audit_log_path = write_init_history_entry(
            project_root,
            action="overwrite-confirmed",
            files_touched=existing_files,
        )
        return (
            GuardOutcome(
                action="overwrite-confirmed",
                existing_files=existing_files,
                audit_log_path=audit_log_path,
                diagnostic=None,
                notes=(
                    f"Explicit override accepted; audit-log written at "
                    f"{audit_log_path}. Scaffolders will overwrite existing "
                    "files."
                ),
            ),
            run_state,
        )

    # Branch 3 — override flag without secondary confirmation.
    if request.override_confirmed and not request.secondary_confirmed:
        diagnostic = _build_halt_diagnostic(
            existing_files=existing_files,
            halt_route="secondary-confirmation-missing",
            extra_hint=(
                "Secondary confirmation missing: `--overwrite-confirmed` "
                "requires `--yes` (or interactive confirmation) to take "
                "effect (epics.md lines 3061-3064)."
            ),
        )
        next_run_state = _emit_marker(
            run_state=run_state,
            marker_registry=marker_registry,
            existing_files=existing_files,
            halt_route="secondary-confirmation-missing",
            note=(
                "init halted: --overwrite-confirmed passed without --yes "
                "secondary confirmation"
            ),
        )
        return (
            GuardOutcome(
                action="halt-would-destroy",
                existing_files=existing_files,
                audit_log_path=None,
                diagnostic=diagnostic,
                notes=(
                    "init halted: secondary confirmation missing for "
                    "explicit override."
                ),
            ),
            next_run_state,
        )

    # Branch 4 — default re-run path; probe merge safety.
    corrupted_path = _probe_merge_safety(project_root, existing_files)
    if corrupted_path is not None:
        diagnostic = _build_halt_diagnostic(
            existing_files=existing_files,
            halt_route="merge-failed",
            extra_hint=(
                f"Merge probe failed: {corrupted_path!s} is malformed YAML. "
                "Restore or delete the file before re-running."
            ),
        )
        next_run_state = _emit_marker(
            run_state=run_state,
            marker_registry=marker_registry,
            existing_files=existing_files,
            halt_route="merge-failed",
            note=(
                f"init halted: existing YAML at {corrupted_path!s} is "
                "malformed; safe additive merge is structurally unavailable"
            ),
        )
        return (
            GuardOutcome(
                action="halt-would-destroy",
                existing_files=existing_files,
                audit_log_path=None,
                diagnostic=diagnostic,
                notes=(
                    "init halted: malformed existing YAML blocks safe "
                    "additive merge."
                ),
            ),
            next_run_state,
        )

    # Default re-run path — preserve-merge.
    return (
        GuardOutcome(
            action="preserve-merge",
            existing_files=existing_files,
            audit_log_path=None,
            diagnostic=None,
            notes=(
                "Existing user-owned content detected. `init` will preserve "
                "your customizations: config + qa-runbook are additively "
                "merged; the existing sample story is preserved as-is. "
                "Pass `--overwrite-confirmed --yes` to reset to canonical "
                "defaults instead."
            ),
        ),
        run_state,
    )


