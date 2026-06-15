"""Story 20.2 — Flakiness-log schema + persistence (FR-P2-8).

The persistence **substrate** for the longitudinal QA flakiness signal: a
per-story, gitignored, append-only store of per-AC pass/fail history
accumulated ACROSS runs at ``_bmad-output/qa-flakiness/{story-id}.yaml``.
FR-P2-8's mandate is "longitudinal, design from real data" — this story
lands the corpus-producing substrate first; the flakiness threshold +
``flakiness-threshold-exceeded`` marker (Story 20.3) is designed against the
corpus, and the reference runs (Story 20.4) witness accumulation to
threshold-exceeded.

Architectural template (clone :mod:`loud_fail_harness.retry_history`):
    ``retry_history`` is the closest sibling — a gitignored, per-story,
    longitudinal-persistence module under ``_bmad-output/``. This module
    replicates its discipline: a single-source-of-truth root constant
    (:data:`FLAKINESS_LOG_ROOT`), ``compute_*_path`` anchored on a
    caller-suppliable repo root with a path-hardened ``story_id``, frozen
    Pydantic v2 models serialized deterministically, and atomic writes.

Atomic-write / H1 decision (AC-4 / AC-5):
    Persistence REUSES the canonical
    :func:`loud_fail_harness.run_state.atomic_write_text` primitive
    (temp-file + ``os.replace``, POSIX-atomic per NFR-R1). It does NOT add a
    sixth ad-hoc ``_atomic_write_text`` copy. The H1 carry-forward
    codification (promoting the helper to ``_shared.py`` + retiring the ~5
    drifting ad-hoc copies) remains Epic 22 / Story 22.5 scope — this
    flakiness store is a clean REUSE, not the trigger to land that broad
    consolidation here.

Sensor-not-advisor / pure substrate (Pattern 5):
    This is a maintainer-data store, NOT a specialist envelope. It RETURNS
    data and PERSISTS data; it emits NO marker, prints nothing (outside the
    validator CLI), and never writes the story doc. The
    ``flakiness-threshold-exceeded`` marker + qa-runbook threshold config +
    ``agents/qa.md`` per-run wiring are ALL Story 20.3 scope.

Architectural placement (load-bearing):
    A substrate **library**, NOT a sixth-counted substrate component. ADR-003
    enumerates exactly five substrate components; this module is a sibling of
    :mod:`retry_history` / :mod:`qa_plan_rederivation` — libraries that grew
    the harness module count without growing the substrate-component count.
    FOUR specialists / THREE hooks / FIVE components held.

``find_repo_root()`` discipline (Epic 1 retro Action #1):
    No path computation runs at module import time. The public helpers accept
    an optional caller-supplied ``repo_root``; when omitted, ``find_repo_root``
    is resolved lazily at call time (never at import).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Final, Literal

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, best_match
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    model_validator,
)

from loud_fail_harness._shared import find_repo_root, load_schema
from loud_fail_harness.input_hardening import harden_identifier, harden_path_segment
from loud_fail_harness.run_state import atomic_write_text

__all__ = [
    "DEFAULT_RETENTION_RUNS",
    "FLAKINESS_LOG_ROOT",
    "SCHEMA_VERSION",
    "FlakinessAcHistory",
    "FlakinessLog",
    "FlakinessLogError",
    "FlakinessRunRecord",
    "allocate_timestamp",
    "append_run_record",
    "compute_flakiness_log_path",
    "load_flakiness_log",
    "main",
    "persist_flakiness_log",
    "validate_flakiness_log",
]

#: Single source of truth for the FR-P2-8 flakiness-log path root,
#: ``_bmad-output/qa-flakiness``. Downstream consumers (Story 20.3 wrapper
#: wiring) read this constant rather than re-typing the literal. Sibling of
#: :data:`loud_fail_harness.retry_history.RETRY_HISTORY_ROOT`.
FLAKINESS_LOG_ROOT: Final[str] = "_bmad-output/qa-flakiness"

#: Default retention: the last N run records per AC. Configurable via the
#: :func:`append_run_record` ``retention`` parameter (append-then-trim-oldest).
#: Any qa-runbook ``flakiness.retention_runs`` config surface is Story 20.3.
DEFAULT_RETENTION_RUNS: Final[int] = 30

#: Closed schema version, mirrored on the closed ``schema_version`` enum in
#: ``schemas/qa-flakiness-log.yaml``.
SCHEMA_VERSION: Final[Literal["1.0"]] = "1.0"

_SCHEMA_FILENAME: Final[str] = "qa-flakiness-log.yaml"


# --------------------------------------------------------------------------- #
# Pydantic models (frozen; field-declaration order load-bearing for byte-     #
# stable model_dump output)                                                   #
# --------------------------------------------------------------------------- #


class FlakinessRunRecord(BaseModel):
    """One per-AC, per-run pass/fail record (AC-1).

    ``retry_count_within_run`` is the ACTION-LEVEL (Playwright-native) retry
    count — the "action-level" tier of the two-tier retry model (prd.md line
    1044), DISTINCT from the orchestrator whole-story retry budget. A run that
    ultimately passed after action-level retries is a flakiness signal even
    though ``status`` is ``pass``.

    ``evidence_ref`` is a pointer into the FR49 qa-evidence tree
    (``_bmad-output/qa-evidence/{story-id}/{run-id}/…``) — NFR-O3 trace
    linkability. It legitimately carries path separators, so it is an
    ``identifier_field`` (whitespace/newline/null rejected) rather than a
    ``path_field``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str = Field(min_length=1)
    timestamp: str = Field(min_length=1)
    status: Literal["pass", "fail"]
    retry_count_within_run: int = Field(ge=0)
    evidence_ref: str = Field(min_length=1)

    @model_validator(mode="after")
    def _harden_identifier_inputs(self) -> FlakinessRunRecord:
        """Input-hardening (Story 24.2 discipline). ``min_length=1`` accepts
        ``"   "``; route the raw-ingress string fields through the shared
        helper to reject whitespace-only / embedded-newline / null-byte
        values. ``timestamp`` format is enforced by the jsonschema ``pattern``
        in ``schemas/qa-flakiness-log.yaml``, NOT by this Pydantic model —
        any non-empty string is accepted here. ``status`` is a closed
        ``Literal`` and ``retry_count_within_run`` is an int — neither is a
        raw hostile-text surface."""
        harden_identifier(self.run_id, "FlakinessRunRecord.run_id")
        harden_identifier(self.evidence_ref, "FlakinessRunRecord.evidence_ref")
        return self


class FlakinessAcHistory(BaseModel):
    """The ordered (oldest -> newest) run history for one AC (AC-1)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ac_id: str = Field(min_length=1)
    runs: tuple[FlakinessRunRecord, ...]

    @model_validator(mode="after")
    def _harden_identifier_inputs(self) -> FlakinessAcHistory:
        harden_identifier(self.ac_id, "FlakinessAcHistory.ac_id")
        return self


class FlakinessLog(BaseModel):
    """The on-disk flakiness-log document for one story (AC-1).

    ``story_id`` composes the on-disk file path
    ``_bmad-output/qa-flakiness/{story-id}.yaml``, so it is a
    ``path_field`` (hardened against separators + ``..`` traversal so it
    cannot escape the umbrella).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0"] = Field(default=SCHEMA_VERSION)
    story_id: str = Field(min_length=1)
    acs: tuple[FlakinessAcHistory, ...]

    @model_validator(mode="after")
    def _harden_path_inputs(self) -> FlakinessLog:
        harden_path_segment(self.story_id, "FlakinessLog.story_id")
        return self


# --------------------------------------------------------------------------- #
# Exceptions                                                                  #
# --------------------------------------------------------------------------- #


class FlakinessLogError(Exception):
    """Raised on a present-but-unreadable/invalid on-disk flakiness log.

    Corrupt-file policy (AC, Dev Notes): absent file -> :func:`load_flakiness_log`
    returns ``None``; present-but-schema-invalid (or unparseable YAML) ->
    loud-fail with this exception so a poisoned longitudinal store surfaces
    rather than silently resetting. The underlying cause is carried via
    ``__cause__``.
    """


# --------------------------------------------------------------------------- #
# Timestamp allocation (injected-clock determinism)                           #
# --------------------------------------------------------------------------- #


def allocate_timestamp(now: datetime | None = None) -> str:
    """Return an ISO-8601 UTC stamp ``YYYY-MM-DDTHH:MM:SSZ`` for a run record.

    Mirrors :func:`loud_fail_harness.qa_evidence_persistence.allocate_run_id`'s
    injected-clock determinism: tests pass an explicit ``now`` rather than
    relying on the wall clock. Uppercase ``T`` + trailing ``Z``; no fractional
    seconds. Matches the ``timestamp`` pattern in ``schemas/qa-flakiness-log.yaml``.
    """
    instant = now if now is not None else datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ValueError(
            "now must be timezone-aware; got a naive datetime. "
            "Use datetime.now(timezone.utc) or pass an aware datetime."
        )
    return instant.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- #
# Path helper                                                                 #
# --------------------------------------------------------------------------- #


def compute_flakiness_log_path(
    story_id: str,
    *,
    repo_root: pathlib.Path | None = None,
) -> pathlib.Path:
    """Return ``{repo_root}/_bmad-output/qa-flakiness/{story_id}.yaml``.

    Pure path computation; does NOT create the file or its parent. ``story_id``
    is path-hardened (separators + ``..`` rejected) so it cannot escape the
    flakiness umbrella. Mirrors
    :func:`loud_fail_harness.retry_history.compute_round_dir` /
    :func:`loud_fail_harness.qa_evidence_persistence.compute_evidence_root`.

    Args:
        story_id: The BMAD story identifier.
        repo_root: Repository root the path is anchored to. Caller-supplied
            (Epic 1 retro Action #1); when ``None``, resolved lazily via
            :func:`find_repo_root` at call time (never at import).
    """
    harden_path_segment(story_id, "story_id")
    base = repo_root if repo_root is not None else find_repo_root()
    return base / FLAKINESS_LOG_ROOT / f"{story_id}.yaml"


# --------------------------------------------------------------------------- #
# Serialization (mirrors retry_history._serialize_round_artifacts)            #
# --------------------------------------------------------------------------- #


def _serialize_flakiness_log(log: FlakinessLog) -> str:
    """Render a :class:`FlakinessLog` as the canonical on-disk YAML body.

    ``model_dump_json`` -> ``json.loads`` -> ``yaml.safe_dump`` (plain YAML,
    NFR-O2; NOT ruamel — no comment round-trip needed). ``sort_keys=False``
    preserves field-declaration order (load-bearing for byte-stable output).
    """
    payload = json.loads(log.model_dump_json(by_alias=False, exclude_none=False))
    return yaml.safe_dump(payload, sort_keys=False, default_flow_style=False)


# --------------------------------------------------------------------------- #
# Load / append / persist                                                     #
# --------------------------------------------------------------------------- #


def load_flakiness_log(
    story_id: str,
    *,
    repo_root: pathlib.Path | None = None,
) -> FlakinessLog | None:
    """Load the on-disk flakiness log for ``story_id``.

    Absent file -> ``None`` (the green "no history yet" path). A present file
    that is unparseable YAML or schema-invalid -> :exc:`FlakinessLogError`
    (loud-fail: a poisoned longitudinal store must surface, not silently
    reset). The corrupt-file policy mirrors the
    :func:`retry_history.resolve_retry_round` loud-fail-on-corrupt posture
    rather than the :func:`qa_a11y_audit.load_baseline` None-on-corrupt
    posture, because a a11y baseline is regenerable per-run while a flakiness
    corpus is irreplaceable longitudinal data.
    """
    path = compute_flakiness_log_path(story_id, repo_root=repo_root)
    try:
        body = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise FlakinessLogError(
            f"flakiness log at {path} unreadable: {exc!r}"
        ) from exc
    try:
        raw = yaml.safe_load(body)
    except yaml.YAMLError as exc:
        raise FlakinessLogError(
            f"flakiness log at {path} did not parse as YAML: {exc!r}"
        ) from exc
    try:
        return FlakinessLog.model_validate(raw)
    except ValidationError as exc:
        raise FlakinessLogError(
            f"flakiness log at {path} did not match the FlakinessLog "
            f"schema: {exc!r}"
        ) from exc


def append_run_record(
    log: FlakinessLog | None,
    *,
    story_id: str,
    ac_id: str,
    record: FlakinessRunRecord,
    retention: int = DEFAULT_RETENTION_RUNS,
) -> FlakinessLog:
    """Pure builder: append ``record`` to ``ac_id``'s history and return the
    new immutable :class:`FlakinessLog`. Performs NO I/O.

    Append-then-trim-oldest: the record is appended to the AC's ``runs``, then
    the AC's ``runs`` is trimmed to the last ``retention`` entries (the AC
    history is created on first sighting). ``log=None`` starts a fresh log for
    ``story_id``.

    Raises:
        ValueError: ``story_id`` is path-unsafe (separator / ``..``
            traversal); ``ac_id`` is whitespace-only or contains embedded
            newlines / null bytes; ``retention < 1``; or ``log`` is non-None
            and its ``story_id`` disagrees with the ``story_id`` argument (a
            cross-story append is a caller bug — loud-fail rather than
            silently mislabel the store).
    """
    harden_path_segment(story_id, "story_id")
    harden_identifier(ac_id, "ac_id")
    if retention < 1:
        raise ValueError(f"retention must be >= 1; got {retention}")
    if log is not None and log.story_id != story_id:
        raise ValueError(
            f"story_id mismatch: log.story_id={log.story_id!r} != "
            f"story_id argument {story_id!r}"
        )

    existing_acs = log.acs if log is not None else ()
    new_acs: list[FlakinessAcHistory] = []
    found = False
    for ac in existing_acs:
        if ac.ac_id == ac_id:
            found = True
            trimmed = (*ac.runs, record)[-retention:]
            new_acs.append(FlakinessAcHistory(ac_id=ac_id, runs=trimmed))
        else:
            new_acs.append(ac)
    if not found:
        new_acs.append(FlakinessAcHistory(ac_id=ac_id, runs=(record,)))

    return FlakinessLog(
        schema_version=SCHEMA_VERSION,
        story_id=story_id,
        acs=tuple(new_acs),
    )


def persist_flakiness_log(
    log: FlakinessLog,
    *,
    repo_root: pathlib.Path | None = None,
) -> None:
    """Serialize ``log`` and write it atomically to its canonical path.

    Reuses :func:`loud_fail_harness.run_state.atomic_write_text` (the canonical
    NFR-R1 temp-file-plus-atomic-rename primitive — NOT a new ad-hoc copy;
    AC-4 / AC-5). The parent directory is created first (``atomic_write_text``
    writes its temp file in the target's directory and does not mkdir).
    Sensor-not-advisor: no marker, no story-doc write.
    """
    path = compute_flakiness_log_path(log.story_id, repo_root=repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, _serialize_flakiness_log(log))


# --------------------------------------------------------------------------- #
# jsonschema validator + CLI (library-as-CLI-aid; NOT a ci.yml gate)          #
# --------------------------------------------------------------------------- #


def _schema_path(repo_root: pathlib.Path | None = None) -> pathlib.Path:
    base = repo_root if repo_root is not None else find_repo_root()
    return base / "schemas" / _SCHEMA_FILENAME


def validate_flakiness_log(
    path: pathlib.Path,
    *,
    schema_path: pathlib.Path | None = None,
) -> int:
    """jsonschema-validate an on-disk flakiness-log file against
    ``schemas/qa-flakiness-log.yaml``.

    Mirrors :func:`sprint_status_artifact_validator.main` /
    :func:`event_validator.main`: ``load_schema`` + ``Draft202012Validator``,
    best-match JSON-pointer diagnostics.

    Returns:
        0 — valid; 1 — schema-invalid (or non-mapping document); 2 —
        harness-level error (file/schema unreadable or unparseable).
    """
    try:
        body = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(
            f"harness-level error: flakiness-log unreadable: {path}: {exc}",
            file=sys.stderr,
        )
        return 2
    try:
        raw = yaml.safe_load(body)
    except yaml.YAMLError as exc:
        print(
            f"harness-level error: flakiness-log YAML parse failure: "
            f"{path}: {exc}",
            file=sys.stderr,
        )
        return 2

    resolved = schema_path if schema_path is not None else _schema_path()
    try:
        schema = load_schema(resolved)
    except OSError as exc:
        print(
            f"harness-level error: schema unreadable: {resolved}: {exc}",
            file=sys.stderr,
        )
        return 2
    except (SchemaError, yaml.YAMLError) as exc:
        print(
            f"harness-level error: schema malformed: {resolved}: {exc}",
            file=sys.stderr,
        )
        return 2

    if not isinstance(raw, dict):
        print(
            f"flakiness-log: {path} did not parse to a YAML mapping at top "
            f"level",
            file=sys.stderr,
        )
        return 1

    error = best_match(Draft202012Validator(schema).iter_errors(raw))
    if error is None:
        print(f"flakiness-log: valid ({path})")
        return 0
    pointer = "/".join(str(part) for part in error.absolute_path) or "<root>"
    print(
        f"flakiness-log: schema violation at {pointer}: {error.message}",
        file=sys.stderr,
    )
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry-point registered as ``flakiness-log-validator`` in
    ``pyproject.toml`` ``[project.scripts]`` — a library-as-CLI-aid (exercised
    by pytest), NOT a ``ci.yml`` gate step.
    """
    parser = argparse.ArgumentParser(
        prog="flakiness-log-validator",
        description=(
            "Validate a QA flakiness-log file against "
            "schemas/qa-flakiness-log.yaml (Story 20.2 / FR-P2-8)."
        ),
    )
    parser.add_argument(
        "path",
        type=pathlib.Path,
        help="Path to a flakiness-log YAML file to validate.",
    )
    parser.add_argument(
        "--schema",
        required=False,
        type=pathlib.Path,
        default=None,
        help=(
            "Optional explicit schema path (defaults to "
            "<repo-root>/schemas/qa-flakiness-log.yaml)."
        ),
    )
    args = parser.parse_args(argv)
    return validate_flakiness_log(args.path, schema_path=args.schema)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
