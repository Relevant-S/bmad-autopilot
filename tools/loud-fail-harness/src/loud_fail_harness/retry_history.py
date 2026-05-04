"""Story 5.5 — Externalized retry history + run-state references.

The FIFTH Epic-5 substrate landing per ``epics.md`` lines 2218-2233 —
sibling of Story 5.1's :mod:`retry_budget`, Story 5.2's
:mod:`retry_router`, Story 5.3's :mod:`retry_dispatch`, and Story
5.4's :mod:`scope_assertion`. The FR13 + NFR-R5 substrate-level claim
CLOSER paired with Story 5.1's :class:`RetryAttempt` MVP-shape opener
and Story 5.6's exhaustion preservation.

Sources:
    * **PRD FR13** (``_bmad-output/planning-artifacts/prd.md`` line 824,
      verbatim): "Orchestrator preserves retry history per round
      (findings + scope + diff) in run-state for downstream PR bundle
      assembly and temporal diagnostic inspection."
    * **PRD NFR-R5** (``prd.md`` line 949, verbatim): "**Retry history
      preservation** — retry history (findings, scope, diff per round)
      is preserved even when retry-budget exhausts and escalation fires;
      history is available via the escalation bundle and via the
      ``status`` command. (Cross-reference: FR13, FR14, FR48.)"
    * **PRD NFR-R8** (``prd.md`` line 952) — cross-state consistency /
      write-ordering. Per-round artifacts on disk are canonical;
      run-state's ``retry_history[]`` reference array is cache. On
      disagreement (path missing), fail loudly via the marker; never
      silent skip.
    * **Story 5.5 verbatim epic AC** at ``epics.md`` lines 2362-2394.
    * **epics.md line 2379** (verbatim, the marker-class-reuse
      rationale): "dangling references (path missing) emit a
      ``dangling-evidence-ref`` marker (Story 1.4 taxonomy, reused —
      same diagnostic surface as evidence dangling refs)".

Marker class:
    The ``dangling-evidence-ref`` marker class is enumerated in
    ``schemas/marker-taxonomy.yaml`` lines 199-206 (Story 1.4 v1
    closed taxonomy). The taxonomy entry's ``diagnostic_pointer``
    (verbatim from line 200-205): "A PR bundle contains an evidence
    reference path that does not resolve to an on-disk artifact.
    Remediation: regenerate the evidence OR fix the reference.
    Distinct from ``orphan-run-state-detected``: dangling-evidence is
    about evidence-file disappearance for a known story; orphan-run-
    state is about run-state for a deleted story-doc." Same diagnostic
    surface as evidence-ref dangling detection (Story 4.12) — a
    referenced on-disk artifact is missing; remediation differs only
    by which artifact (retry-round vs. evidence) but the diagnostic
    shape is identical. The absence of a NEW marker class for retry-
    history-specific dangling-refs IS the structural enforcement of
    the marker-class-reuse principle from Story 1.11 (recorded in
    ``docs/extension-audit.md``).

Composition with Story 2.2 :func:`advance_run_state`:
    THIS module's :func:`persist_retry_round` does NOT directly call
    :func:`advance_run_state`. It writes per-round artifacts to disk
    and returns a :class:`RetryAttemptRef`; the orchestrator-skill
    threads the ref through a :data:`StoryDocCallback` supplied to
    :func:`advance_run_state`. The "per-round artifact-write success
    BEFORE run-state advance" ordering invariant (NFR-R8) is enforced
    by that wrapping pattern. Canonical pattern::

        from loud_fail_harness.retry_history import persist_retry_round
        from loud_fail_harness.run_state import (
            advance_run_state,
            RetryAttempt,
            StoryDocCallbackBlocked,
            StoryDocCallbackResult,
        )

        def _retry_round_callback() -> StoryDocCallbackResult:
            try:
                ref = persist_retry_round(
                    round=round_artifacts,
                    repo_root=repo_root,
                    story_id=story_id,
                )
            except Exception as exc:
                raise StoryDocCallbackBlocked(
                    f"persist_retry_round failed: {exc!r}"
                ) from exc
            return StoryDocCallbackResult(accepted=True)

        # Caller threads `ref` into next_state.retry_history before
        # advance_run_state writes it.
        advance_run_state(
            run_state_path=run_state_path,
            next_state=next_state,
            story_doc_callback=_retry_round_callback,
        )

Composition with Story 5.1 :class:`RetryAttempt`:
    THIS module thickens :class:`RetryAttempt` additively (the
    ``round_id`` + ``path`` optional fields). It does NOT replace,
    duplicate, or shadow the model. :class:`RetryAttemptRef` is a
    public-API mirror exposed for clarity; the on-run-state model is
    :class:`RetryAttempt` thickened.

Forward-pointer: Story 5.6 (retry-budget-exhausted non-advance):
    Retry-history artifacts SURVIVE the retry-budget-exhaustion
    non-advance per FR13 + NFR-R5 verbatim. The ``_bmad-output/retry-
    history/`` directory is gitignored but filesystem-persistent; it
    is NOT auto-cleaned by Story 2.11's merge-ready cleanup hook
    (exhaustion does not reach merge-ready per FR14).

Forward-pointer: Story 5.8 (escalation-bundle assembly):
    The escalation-bundle assembler consumes :func:`resolve_retry_round`
    to render per-round summaries in the bundle's "retry history"
    section. The rendering format (markdown? YAML?) is Story 5.8's
    surface, NOT this module's. THIS module returns a typed
    :class:`RetryRoundArtifacts` instance per ref; the assembler owns
    the prose shape.

Forward-pointer: Story 8.x (resumability):
    SessionStart reattachment lazy-loads references via
    :func:`resolve_retry_round`; dangling references emit the
    :data:`DANGLING_EVIDENCE_REF_MARKER` per the same code path the
    CLI uses.

Pluggability invariant (FR62):
    This module lives at ``tools/loud-fail-harness/src/loud_fail_harness/
    retry_history.py`` (the harness substrate). The FR62 pluggability
    gate (:mod:`pluggability_gate`) scans only ``agents/*.md``
    specialist subagent files; it does NOT scan harness substrate.
    Downstream callers compose against THIS module AS DATA per
    ADR-001's portable-surface boundary.

Sensor-not-advisor invariant (FR52 / ADR-002 invariant 1):
    THIS module is FLOW-POLICY territory (orchestrator's job).
    Specialists do not call it; specialists are REPORTED-ON via the
    persisted artifacts. :func:`detect_dangling_refs` returns the
    dangling set; it does NOT emit markers, log, or print. The
    consumer (CLI, Story 8.4 status command, Story 5.8 escalation-
    bundle assembler) decides emission.

NFR-R8 cross-state consistency invariant:
    Per-round artifacts on disk are canonical; run-state's
    ``retry_history[]`` is cache. On disagreement (path missing),
    fail loudly via the marker (via the consumer's emission path);
    never silent-skip.

Architectural placement (load-bearing):
    THIS module is a substrate **library**, NOT a sixth-counted
    substrate component. ADR-003 enumerates exactly five substrate
    components (envelope_validator / event_validator / reconciler /
    enumeration_check / fixture_coverage). :mod:`retry_history` is a
    sibling of :mod:`run_state`, :mod:`qa_evidence_persistence`,
    :mod:`retry_dispatch`, :mod:`scope_assertion` — all substrate
    libraries that grew the harness module count without growing the
    substrate-component count.

``find_repo_root()`` discipline (Epic 1 retro Action #1):
    No path computation in this module calls ``find_repo_root()`` at
    module import time. All public helpers accept ``repo_root`` as a
    caller-supplied parameter; only :func:`_main` resolves
    ``find_repo_root()`` lazily at call time when ``--repo-root`` is
    not provided.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import secrets
import sys
from collections.abc import Callable, Sequence
from typing import Any, ClassVar, Final, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.run_state import RetryAttempt

__all__ = [
    "ArtifactWriter",
    "DanglingRetryRoundRef",
    "RetryAttemptRef",
    "RetryHistoryError",
    "RetryRoundArtifacts",
    "compute_artifacts_path",
    "compute_round_dir",
    "default_artifact_writer",
    "detect_dangling_refs",
    "persist_retry_round",
    "resolve_retry_round",
]


#: Marker class identifier (consumed AS-IS from
#: ``schemas/marker-taxonomy.yaml`` line 199; same source-of-truth
#: posture as :data:`loud_fail_harness.qa_evidence_persistence.EVIDENCE_TRUNCATED_MARKER`).
#: REUSED here per the verbatim epic AC at ``epics.md`` line 2379;
#: the absence of a NEW marker class is structural enforcement of
#: the Story 1.11 marker-class-reuse principle.
DANGLING_EVIDENCE_REF_MARKER: Final[Literal["dangling-evidence-ref"]] = (
    "dangling-evidence-ref"
)

#: Verbatim remediation hint substring sourced from
#: ``schemas/marker-taxonomy.yaml`` line 202 ("Remediation: regenerate
#: the evidence OR fix the reference"). Surfaced on
#: :exc:`DanglingRetryRoundRef`'s message per NFR-O5 (named diagnostic
#: with actionable remediation pointer).
_DANGLING_REMEDIATION_HINT: Final[str] = (
    "regenerate the evidence OR fix the reference"
)

#: The canonical literal for the FR13 / NFR-R5 retry-history-path
#: root, ``_bmad-output/retry-history``. Single source of truth:
#: downstream consumers (Story 5.8 bundle assembler, Story 8.x
#: resumability) read this constant rather than re-typing the literal.
RETRY_HISTORY_ROOT: Final[str] = "_bmad-output/retry-history"


# --------------------------------------------------------------------------- #
# Pydantic models                                                             #
# --------------------------------------------------------------------------- #


class RetryRoundArtifacts(BaseModel):
    """The on-disk artifact shape for one retry round (one ``.yaml``
    document per ``round-NN`` directory; the canonical persisted
    shape).

    Frozen + ``extra="forbid"``; field declaration order is load-
    bearing for byte-stable ``model_dump_json()`` output (parallel to
    :class:`RetryAttempt` / :class:`LastRetryDirective` discipline).

    The ``findings`` field's ``tuple[dict[str, Any], ...]`` element
    type is the documented MVP-opacity exception (the findings shape
    is opaque at MVP per Story 5.8's deferred tightening). Practitioners
    treat the inner dicts as conventionally-immutable; ``frozen=True``
    blocks attribute reassignment but NOT in-place dict mutation.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    round_id: str = Field(min_length=1, pattern=r"^round-\d{2}$")
    retry_attempt: int = Field(ge=1)
    findings: tuple[dict[str, Any], ...]
    scope_affected_files: tuple[str, ...] = Field(min_length=1)
    scope_expanded_to: tuple[str, ...]
    actual_diff_files: tuple[str, ...]
    created_at: str = Field(min_length=1)


class RetryAttemptRef(BaseModel):
    """The run-state-side reference shape; the additive fields on
    :class:`loud_fail_harness.run_state.RetryAttempt` mirror this shape
    exactly.

    Named separately from :class:`RetryAttempt` for clarity in the
    public API — the actual on-run-state model is :class:`RetryAttempt`
    thickened (Story 5.5 AC-2). :meth:`to_retry_attempt` converts to
    the run-state-side model.

    Frozen + ``extra="forbid"``; field declaration order is load-
    bearing for byte-stable ``model_dump_json()`` output.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    retry_attempt: int = Field(ge=1)
    retry_reason: str = Field(min_length=1)
    round_id: str = Field(min_length=1, pattern=r"^round-\d{2}$")
    path: str = Field(min_length=1)

    def to_retry_attempt(self) -> RetryAttempt:
        """Convert to the run-state-side :class:`RetryAttempt` model
        with the Story 5.5 thickened fields populated."""
        return RetryAttempt(
            retry_attempt=self.retry_attempt,
            retry_reason=self.retry_reason,
            round_id=self.round_id,
            path=self.path,
        )


# --------------------------------------------------------------------------- #
# Exceptions                                                                  #
# --------------------------------------------------------------------------- #


class RetryHistoryError(Exception):
    """Base exception for the :mod:`loud_fail_harness.retry_history`
    surface.

    Raised on artifact-corruption (YAML-parse failure or schema-
    mismatch); distinct from :exc:`DanglingRetryRoundRef` (which
    signals a missing artifact). The lineage is load-bearing — a
    corrupted artifact is recoverable by manual inspection, while a
    missing one is recoverable by regeneration; remediation differs.
    """


class DanglingRetryRoundRef(RetryHistoryError):
    """Raised by :func:`resolve_retry_round` when the on-disk artifact
    referenced by a :class:`RetryAttemptRef` does not exist.

    Carries :attr:`marker_class` ClassVar = ``"dangling-evidence-ref"``
    sourced VERBATIM from ``schemas/marker-taxonomy.yaml`` line 199
    (REUSE per the verbatim epic AC at ``epics.md`` line 2379) AND a
    :attr:`ref` attribute carrying the offending
    :class:`RetryAttemptRef`. Per NFR-O5: the message includes the
    offending path + the remediation hint substring "regenerate the
    evidence OR fix the reference" (verbatim from
    ``marker-taxonomy.yaml`` line 202).
    """

    marker_class: ClassVar[Literal["dangling-evidence-ref"]] = (
        "dangling-evidence-ref"
    )

    def __init__(self, *, ref: RetryAttemptRef) -> None:
        self.ref = ref
        super().__init__(
            f"dangling-evidence-ref: retry-round artifact missing at "
            f"{ref.path!r} (round_id={ref.round_id}, "
            f"retry_attempt={ref.retry_attempt}). "
            f"Remediation: {_DANGLING_REMEDIATION_HINT}."
        )


# --------------------------------------------------------------------------- #
# ArtifactWriter type alias + default writer                                  #
# --------------------------------------------------------------------------- #


#: Type alias for the on-disk artifact-writer interface. Signature:
#: ``(target_path, body) -> None``. Implementations write ``body`` to
#: ``target_path`` atomically (mirrors
#: :func:`loud_fail_harness.run_state.advance_run_state`'s temp-file-
#: plus-atomic-rename primitive). Tests inject in-memory writers;
#: production uses :func:`default_artifact_writer`.
ArtifactWriter = Callable[[pathlib.Path, str], None]


def default_artifact_writer(target_path: pathlib.Path, body: str) -> None:
    """Write ``body`` to ``target_path`` atomically via the temp-file-
    plus-atomic-rename pattern.

    Mirrors :func:`loud_fail_harness.run_state.advance_run_state`'s
    OS-level flow byte-for-byte (NFR-R1's atomicity primitive):
    ``target_path.parent.mkdir(parents=True, exist_ok=True)`` →
    ``os.open(O_WRONLY | O_CREAT | O_EXCL)`` → write → ``os.fsync`` →
    close → ``os.replace``. Temp-file path uses the same collision-
    resistant suffix pattern (``<target>.tmp.<pid>.<token_hex>``).
    Cleanup on failure: ``temp_path.unlink(missing_ok=True)`` before
    re-raise.

    On any exception between temp-write and the successful
    ``os.replace``, the temp file is unlinked and the exception
    propagates verbatim. The on-disk state is never partial: either
    the prior file is in place (and no temp file remains after
    cleanup), or the new file is in place (post-replace).

    Args:
        target_path: Absolute or repo-rooted ``pathlib.Path`` to the
            target artifact file.
        body: UTF-8-encoded body to write.
    """
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_name(
        f"{target_path.name}.tmp.{os.getpid()}.{secrets.token_hex(4)}"
    )
    try:
        fd = os.open(
            temp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644
        )
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(body)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp_path, target_path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


# --------------------------------------------------------------------------- #
# Path helpers                                                                #
# --------------------------------------------------------------------------- #


def compute_round_dir(
    *,
    repo_root: pathlib.Path,
    story_id: str,
    round_id: str,
) -> pathlib.Path:
    """Return the per-round dir
    ``{repo_root}/_bmad-output/retry-history/{story_id}/{round_id}``.

    Pure path computation; does NOT create the directory. Mirrors
    :func:`loud_fail_harness.qa_evidence_persistence.compute_run_dir`
    in shape (FR49 → FR13 path-discipline parallel).

    Args:
        repo_root: The repository root the per-round dir is anchored
            to. Caller-supplied per the Epic 1 retro Action #1
            discipline.
        story_id: The BMAD story identifier.
        round_id: The round identifier (matches ``^round-\\d{2}$``).

    Returns:
        ``pathlib.Path`` representing
        ``{repo_root}/_bmad-output/retry-history/{story_id}/{round_id}``.

    Raises:
        ValueError: ``story_id`` empty / absolute / contains ``..``;
            ``round_id`` empty / absolute / contains ``..``.
    """
    if not story_id:
        raise ValueError("story_id must not be empty")
    _story_pure = pathlib.PurePosixPath(story_id)
    if _story_pure.is_absolute():
        raise ValueError(
            f"story_id must not be an absolute path; got {story_id!r}"
        )
    if ".." in _story_pure.parts:
        raise ValueError(
            f"story_id must not contain '..' path traversal segments; "
            f"got {story_id!r}"
        )
    if not round_id:
        raise ValueError("round_id must not be empty")
    _round_pure = pathlib.PurePosixPath(round_id)
    if _round_pure.is_absolute():
        raise ValueError(
            f"round_id must not be an absolute path; got {round_id!r}"
        )
    if ".." in _round_pure.parts:
        raise ValueError(
            f"round_id must not contain '..' path traversal segments; "
            f"got {round_id!r}"
        )
    return repo_root / RETRY_HISTORY_ROOT / story_id / round_id


def compute_artifacts_path(round_dir: pathlib.Path) -> pathlib.Path:
    """Return ``round_dir / "artifacts.yaml"``.

    Single-file-per-round at MVP; future stories may split into
    ``findings.yaml`` + ``scope.yaml`` + ``diff.patch`` as an additive
    thickening (the directory shape allows additive-only growth).
    """
    return round_dir / "artifacts.yaml"


# --------------------------------------------------------------------------- #
# Serialization helper (mirrors run_state._serialize_run_state)               #
# --------------------------------------------------------------------------- #


def _serialize_round_artifacts(round: RetryRoundArtifacts) -> str:
    """Render a :class:`RetryRoundArtifacts` instance as the canonical
    on-disk YAML body.

    Pipeline mirrors :func:`loud_fail_harness.run_state._serialize_run_state`:
    ``model_dump_json`` → ``json.loads`` → ``yaml.safe_dump``. The JSON
    roundtrip canonicalizes Python types into JSON-Schema-compatible
    primitives before YAML dumping. ``sort_keys=False`` preserves
    Pydantic's field-declaration order (load-bearing for byte-stable
    output).
    """
    json_str = round.model_dump_json(by_alias=False, exclude_none=False)
    payload: dict[str, Any] = json.loads(json_str)
    return yaml.safe_dump(payload, sort_keys=False, default_flow_style=False)


# --------------------------------------------------------------------------- #
# Persistence + resolution + dangling-detection                               #
# --------------------------------------------------------------------------- #


def persist_retry_round(
    *,
    round: RetryRoundArtifacts,
    repo_root: pathlib.Path,
    story_id: str,
    retry_reason: str,
    writer: ArtifactWriter | None = None,
) -> RetryAttemptRef:
    """Persist ``round`` to its canonical on-disk location and return
    the run-state-side :class:`RetryAttemptRef`.

    Computes the round dir + artifacts path, serializes ``round`` to
    YAML, and invokes ``writer`` (defaults to
    :func:`default_artifact_writer`). Returns a :class:`RetryAttemptRef`
    whose ``path`` is repo-relative posix-style (the run-state YAML's
    portability surface uses string-typed paths).

    The "per-round artifact-write success BEFORE run-state advance"
    ordering invariant (NFR-R8) is NOT enforced inside this function;
    it is enforced by the orchestrator-skill's composition pattern
    that wraps THIS function inside a :data:`StoryDocCallback` supplied
    to :func:`loud_fail_harness.run_state.advance_run_state`. See the
    module docstring's "Composition with Story 2.2" section for the
    canonical pattern.

    Args:
        round: The :class:`RetryRoundArtifacts` instance to persist.
            Pre-validated by Pydantic at construction time
            (``round_id`` pattern + ``scope_affected_files`` non-empty
            invariants enforced by the model).
        repo_root: The repository root the per-round dir is anchored
            to. Caller-supplied per Epic 1 retro Action #1.
        story_id: The BMAD story identifier.
        retry_reason: The retry reason string (sourced from the
            orchestrator's Story 5.2 bucket-routing decision; persisted
            in the returned :class:`RetryAttemptRef` for run-state
            cache use).
        writer: Optional :data:`ArtifactWriter` for test injection.
            Defaults to :func:`default_artifact_writer`.

    Returns:
        :class:`RetryAttemptRef` carrying the on-disk path (repo-
        relative, posix-style) and the round identifier; the caller
        threads it through :func:`advance_run_state` as a thickened
        :class:`RetryAttempt` entry on ``next_state.retry_history``.

    Raises:
        ValueError: ``story_id`` empty / contains ``..``; ``round_id``
            empty / contains ``..`` (raised by :func:`compute_round_dir`).
        Exception: any exception the writer raises propagates verbatim
            (no swallowing per Pattern 5 / loud-fail discipline).
    """
    effective_writer = writer if writer is not None else default_artifact_writer
    round_dir = compute_round_dir(
        repo_root=repo_root, story_id=story_id, round_id=round.round_id
    )
    artifacts_path = compute_artifacts_path(round_dir)
    body = _serialize_round_artifacts(round)
    effective_writer(artifacts_path, body)
    rel_path = (
        pathlib.PurePosixPath(RETRY_HISTORY_ROOT)
        / story_id
        / round.round_id
        / "artifacts.yaml"
    )
    return RetryAttemptRef(
        retry_attempt=round.retry_attempt,
        retry_reason=retry_reason,
        round_id=round.round_id,
        path=str(rel_path),
    )


def resolve_retry_round(
    *,
    ref: RetryAttemptRef,
    repo_root: pathlib.Path,
) -> RetryRoundArtifacts:
    """Lazy-load the on-disk :class:`RetryRoundArtifacts` referenced
    by ``ref``.

    Reads ``repo_root / ref.path`` (the path is repo-root-relative;
    posix-style strings interpreted via :class:`pathlib.PurePosixPath`
    for cross-OS portability). On ``FileNotFoundError``, raises
    :exc:`DanglingRetryRoundRef` with the marker-class identifier +
    remediation hint. On YAML-parse failure, raises
    :exc:`RetryHistoryError` whose ``__cause__`` is the underlying
    ``yaml.YAMLError``. On schema-mismatch (Pydantic
    :exc:`ValidationError`), raises :exc:`RetryHistoryError` whose
    ``__cause__`` is the validation error.

    The exception lineage distinguishes "missing artifact"
    (recoverable by regeneration) from "corrupted artifact"
    (recoverable by manual inspection); the consumer (CLI, status
    command, escalation bundle) chooses remediation accordingly.

    Args:
        ref: The :class:`RetryAttemptRef` to resolve.
        repo_root: The repository root the ref's path is anchored to.

    Returns:
        :class:`RetryRoundArtifacts` parsed from the on-disk YAML.

    Raises:
        RetryHistoryError: ``ref.path`` is absolute or contains ``..``
            (traversal guard); or the on-disk artifact is unparseable
            or schema-invalid (carries the underlying cause via
            ``__cause__``).
        DanglingRetryRoundRef: The on-disk artifact is missing.
    """
    pure = pathlib.PurePosixPath(ref.path)
    if pure.is_absolute() or ".." in pure.parts:
        raise RetryHistoryError(
            f"retry-round ref path {ref.path!r} contains traversal "
            f"sequences or is absolute; refusing to resolve outside "
            f"repo_root"
        )
    target = repo_root / pure
    try:
        body = target.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise DanglingRetryRoundRef(ref=ref) from exc
    try:
        raw = yaml.safe_load(body)
    except yaml.YAMLError as exc:
        raise RetryHistoryError(
            f"retry-round artifact at {ref.path!r} did not parse as "
            f"YAML: {exc!r}"
        ) from exc
    try:
        return RetryRoundArtifacts.model_validate(raw)
    except ValidationError as exc:
        raise RetryHistoryError(
            f"retry-round artifact at {ref.path!r} did not match "
            f"RetryRoundArtifacts schema: {exc!r}"
        ) from exc


def detect_dangling_refs(
    *,
    refs: tuple[RetryAttemptRef, ...],
    repo_root: pathlib.Path,
) -> tuple[RetryAttemptRef, ...]:
    """Walk ``refs`` and return the subset whose on-disk artifacts are
    missing (in input-order).

    Pure: does NOT raise (corrupted-but-present artifacts are NOT
    classified as dangling — "dangling" specifically means "missing");
    does NOT emit markers; does NOT log; does NOT print. Sensor-not-
    advisor: the returned tuple IS the diagnostic; the consumer
    decides emission. Empty tuple iff all refs resolve cleanly OR all
    refs are corrupted-but-present (the consumer separately surfaces
    corruption).

    Args:
        refs: The tuple of :class:`RetryAttemptRef` to scan.
        repo_root: The repository root.

    Returns:
        Tuple of dangling refs in input-order (empty if none).
    """
    dangling: list[RetryAttemptRef] = []
    for ref in refs:
        try:
            resolve_retry_round(ref=ref, repo_root=repo_root)
        except DanglingRetryRoundRef:
            dangling.append(ref)
        except RetryHistoryError:
            # Corrupted-but-present artifact is NOT dangling per the
            # AC-5 contract; silently exclude. The CLI consumer
            # surfaces both kinds separately.
            continue
    return tuple(dangling)


def _detect_corrupted_refs(
    *,
    refs: tuple[RetryAttemptRef, ...],
    repo_root: pathlib.Path,
) -> tuple[RetryAttemptRef, ...]:
    """Walk ``refs`` and return those whose on-disk artifacts are
    present but corrupt (YAML-parse failure or schema-mismatch).

    Private; not in ``__all__``. Complements :func:`detect_dangling_refs`:
    "missing" (dangling) vs "present-but-corrupt" are distinct failure
    modes requiring different remediation. Called by :func:`_main` to
    surface both kinds. Does NOT raise; does NOT emit markers.
    """
    corrupted: list[RetryAttemptRef] = []
    for ref in refs:
        try:
            resolve_retry_round(ref=ref, repo_root=repo_root)
        except DanglingRetryRoundRef:
            pass
        except RetryHistoryError:
            corrupted.append(ref)
    return tuple(corrupted)


# --------------------------------------------------------------------------- #
# CLI entry-point                                                             #
# --------------------------------------------------------------------------- #


def _format_clean_message(rounds_checked: int) -> str:
    return f"retry-history: clean (rounds={rounds_checked})"


def _format_dangling_block(
    dangling: tuple[RetryAttemptRef, ...],
) -> str:
    """Render the multi-line stderr block emitted on dangling-
    detection. Format is byte-stable for the AC-6 hook-integration
    test consumers.
    """
    lines = [
        f"dangling-evidence-ref: marker_class={DANGLING_EVIDENCE_REF_MARKER}",
        f"dangling_count={len(dangling)}",
        "dangling_refs:",
    ]
    for ref in dangling:
        lines.append(
            f"  - round_id={ref.round_id} "
            f"retry_attempt={ref.retry_attempt} path={ref.path!r}"
        )
    lines.append(f"Remediation: {_DANGLING_REMEDIATION_HINT}.")
    return "\n".join(lines)


def _main(argv: Sequence[str] | None = None) -> int:
    """CLI entry-point registered as ``retry-history-resolve`` in
    ``pyproject.toml`` ``[project.scripts]``.

    Reads run-state YAML from ``--run-state PATH``; parses the
    ``retry_history`` array; filters to entries with non-None ``path``
    AND non-None ``round_id`` (the externalized refs; pre-thickening
    MVP entries without both fields are skipped silently — they
    predate this story and are NOT dangling); invokes
    :func:`detect_dangling_refs` and :func:`_detect_corrupted_refs`.

    Exit codes:
        0 — all thickened refs resolved cleanly (dangling=0, corrupt=0).
        1 — dangling or corrupted refs found; OR run-state read/parse
            failed; OR a thickened entry failed :class:`RetryAttemptRef`
            validation (the entry is suspicious: has path+round_id but
            is otherwise malformed).

    Output format is byte-stable for AC-6 hook-integration test
    consumers. Mirrors
    :func:`loud_fail_harness.scope_assertion._main`'s argparse + exit-
    code pattern verbatim (Story 5.4 precedent).
    """
    parser = argparse.ArgumentParser(
        prog="retry-history-resolve",
        description=(
            "Resolve externalized retry-history references against on-"
            "disk artifacts; emit dangling-evidence-ref diagnostic on "
            "missing paths (Story 5.5 / FR13 + NFR-R5)."
        ),
    )
    parser.add_argument(
        "--run-state",
        required=True,
        type=pathlib.Path,
        help="Path to run-state.yaml (e.g. _bmad/automation/run-state.yaml).",
    )
    parser.add_argument(
        "--repo-root",
        required=False,
        type=pathlib.Path,
        default=None,
        help=(
            "Repo root for retry-history artifact resolution (defaults "
            "to find_repo_root() at call time)."
        ),
    )
    args = parser.parse_args(argv)

    run_state_path: pathlib.Path = args.run_state
    repo_root: pathlib.Path = args.repo_root or find_repo_root()

    try:
        raw_text = run_state_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(
            f"retry-history-resolve: run-state not found at "
            f"{run_state_path}; nothing to resolve.",
            file=sys.stderr,
        )
        return 1
    except OSError as exc:
        print(
            f"retry-history-resolve: could not read run-state at "
            f"{run_state_path}: {exc!r}",
            file=sys.stderr,
        )
        return 1

    try:
        raw = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        print(
            f"retry-history-resolve: run-state at {run_state_path} did "
            f"not parse as valid YAML: {exc!r}",
            file=sys.stderr,
        )
        return 1

    if not isinstance(raw, dict):
        print(
            f"retry-history-resolve: run-state at {run_state_path} did "
            f"not parse to a YAML mapping; nothing to resolve.",
            file=sys.stderr,
        )
        return 1

    history_raw = raw.get("retry_history") or []
    if not isinstance(history_raw, list):
        history_raw = []

    refs: list[RetryAttemptRef] = []
    has_malformed_thickened = False
    for entry in history_raw:
        if not isinstance(entry, dict):
            continue
        entry_path = entry.get("path")
        entry_round = entry.get("round_id")
        if not entry_path or not entry_round:
            # Pre-thickening MVP entry (no path/round_id); predates
            # externalization and is NOT dangling.
            continue
        # Thickened entry: validate retry_reason before constructing ref.
        entry_reason = entry.get("retry_reason")
        if not entry_reason:
            print(
                f"retry-history-resolve: malformed thickened entry "
                f"(missing retry_reason) at round_id={entry_round!r} — "
                f"cannot check for dangling; treating as suspicious.",
                file=sys.stderr,
            )
            has_malformed_thickened = True
            continue
        # Safe int conversion for retry_attempt (avoid silent 0→1 coercion).
        raw_attempt = entry.get("retry_attempt")
        try:
            entry_attempt = int(raw_attempt) if raw_attempt is not None else 1
        except (TypeError, ValueError):
            entry_attempt = 1
        try:
            ref = RetryAttemptRef(
                retry_attempt=entry_attempt,
                retry_reason=str(entry_reason),
                round_id=str(entry_round),
                path=str(entry_path),
            )
        except (ValidationError, TypeError, ValueError) as exc:
            print(
                f"retry-history-resolve: malformed thickened "
                f"retry_history entry {entry!r}: {exc!r} — "
                f"cannot check for dangling; treating as suspicious.",
                file=sys.stderr,
            )
            has_malformed_thickened = True
            continue
        refs.append(ref)

    refs_tuple = tuple(refs)
    dangling = detect_dangling_refs(refs=refs_tuple, repo_root=repo_root)
    corrupted = _detect_corrupted_refs(refs=refs_tuple, repo_root=repo_root)

    if not dangling and not corrupted and not has_malformed_thickened:
        print(_format_clean_message(rounds_checked=len(refs_tuple)))
        return 0

    if dangling:
        print(_format_dangling_block(dangling), file=sys.stderr)
    if corrupted:
        lines = [
            "retry-history-corrupted: corrupt on-disk artifacts detected",
            f"corrupted_count={len(corrupted)}",
            "corrupted_refs:",
        ]
        for ref in corrupted:
            lines.append(
                f"  - round_id={ref.round_id} "
                f"retry_attempt={ref.retry_attempt} path={ref.path!r}"
            )
        lines.append(
            "Remediation: inspect the artifact YAML manually; "
            "regenerate if necessary."
        )
        print("\n".join(lines), file=sys.stderr)
    return 1
