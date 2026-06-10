"""Per-seam state-streaming substrate library (Story 2.12).

## Substrate-library identity

THIS module is a substrate **library** — NOT a sixth substrate component.
ADR-003 Consequence 1 enumerates exactly five substrate components
(architecture.md lines 311-315); this module is a library consumed by
Stories 2.5 / 2.6 / 2.7 (orchestrator integration site) + 8.1 (event-log
replay) + 5.5 / 6.4 / 6.5 / 6.7 (Phase 1.5+ retry / cost / marker-
streaming consumers). The substrate-component count stays at FIVE; the
harness module count grows from 21 to 22. Mirrors the Story 1.10b /
2.2 / 2.3 / 2.4 / 2.5 / 2.6 / 2.11 substrate-library precedent.

## Input contract

    * ``event_log_path`` — :class:`pathlib.Path` for the JSONL append
      target. Caller-supplied per Epic 1 retro Action #1 (no
      ``find_repo_root()`` at module top-level). The orchestrator skill
      at runtime resolves to
      ``_bmad-output/qa-evidence/{story_id}/{run_id}/events.jsonl`` via
      :func:`default_event_log_path`.
    * ``stream`` — :class:`TextIO` for the per-event terminal render.
      Defaults to :data:`sys.stdout` for the live-terminal posture per
      NFR-O1; tests pass :class:`io.StringIO` for capture.
    * ``fsync`` — ``bool``; defaults to ``True`` for the per-event
      durability posture per Pattern 4 + ADR-005 Sub-decision (c). Tests
      pass ``False`` for ``tmp_path`` speed.

## Output contract

    * The :func:`make_event_log_appender` factory returns an
      :data:`loud_fail_harness.lifecycle_state_machine.EventLogAppender`
      callable conforming to the Story 2.4 type alias verbatim (signature
      ``(event: dict[str, Any]) -> None``).
    * The closure performs two writes per invocation in this load-bearing
      order: (1) appends one JSONL line to ``event_log_path``;
      (2) writes ``format_event_for_stream(event) + "\\n"`` to ``stream``.
      JSONL FIRST / terminal SECOND is the durability invariant per AC-4
      (a crash between writes leaves the canonical record on disk).

## Streaming format

Per AC-3: ``<HH:MM:SS> [<event_class>] <brief_detail>``. The timestamp is
the event's ``timestamp`` field truncated to ``HH:MM:SS`` (the date is
omitted for terminal brevity; the full ISO-8601 timestamp is preserved
on the JSONL log line). The ``event_class`` is the kebab-case identifier
verbatim per Pattern 1 + Pattern 3. The ``brief_detail`` is a per-class
one-line summary derived from the event's required fields via the
:data:`_BRIEF_DETAIL_RENDERERS` dispatch table.

Forward-compat with Epic 6 marker thickening: unknown event classes
fall through to the generic fallback render ``[<event_class>] <event_id>``.
Future stories (Epic 6 / Story 6.5 / Story 6.7) extend the dispatch table
by adding new branches; existing branches are NOT touched. Per the
verbatim epic AC at epics.md Story 2.12 lines 1551-1553, "Epic 2's
streaming events do NOT include marker emissions beyond what Story 2.6
emits structurally"; the unknown-class fallback IS the forward-compat
extension point.

## Why JSONL ``open("a")`` (not ``tempfile`` + ``os.replace``)

The events.jsonl file is APPEND-ONLY single-writer per ADR-001
("orchestrator emits one of these at every seam transition"). The
per-line append is atomic at the OS layer for sub-PIPE_BUF write sizes;
the rename-after-write protocol from
:func:`loud_fail_harness.specialist_dispatch.persist_dispatch_log` is
correct for that file (REPLACED on each call) but wrong for an
append-only log (APPENDED on each call). The fsync per event is the
durability invariant; the rename pattern would be both overkill and
break the append semantics. Pattern 4's atomic-write discipline is
honored at the per-line granularity, NOT per-file.

## Why the closure does NOT re-validate events

Sensor-not-advisor (Pattern 5) + the 3-caller rule (Epic 1 retro Insight
#4): the upstream emitters
(:func:`loud_fail_harness.lifecycle_state_machine.commit_transition`,
:func:`loud_fail_harness.specialist_dispatch.make_specialist_dispatched_event`,
:func:`loud_fail_harness.specialist_dispatch.make_specialist_returned_event`)
already validate against ``schemas/orchestrator-event.yaml``. THIS
module's substrate trusts the input is schema-valid; double-validation
is waste and creates a feedback loop where THIS story would catch
upstream bugs the upstream tests would miss. The substrate's own
diagnostic surface is :exc:`OSError` propagation per Pattern 5.

## Cross-references

    * Story 2.4 :mod:`loud_fail_harness.lifecycle_state_machine` — the
      :data:`EventLogAppender` type alias (line 309) THIS module's
      factory returns conforming closures for; the
      :func:`commit_transition` (line 752) and :func:`record_halt`
      (line 830) call sites that invoke the appender.
    * Story 2.5 :mod:`loud_fail_harness.orchestrator_run_entry` —
      :func:`run_story_loop_entry` threads the caller-supplied appender
      through the six-step entry sequence; THIS story's factory is the
      production composition site invoked by
      ``skills/bmad-automation/steps/run.md``.
    * Story 2.6 :mod:`loud_fail_harness.specialist_dispatch` —
      :func:`make_specialist_dispatched_event` and
      :func:`make_specialist_returned_event` produce events fed to the
      appender at every dispatch + return seam per
      ``skills/bmad-automation/steps/dispatch.md``.
    * Story 2.11 :mod:`loud_fail_harness.bundle_assembly` — does NOT
      consume events.jsonl at Epic 2 scope (per Story 2.11 AC-5,
      bundle assembly reads ONLY the per-specialist logs); future
      Stories 5.5 / 6.4 / 6.5 add event-log consumption.
    * Story 8.1 — SessionStart reattachment will replay events.jsonl
      to reconstruct in-flight run-state per ADR-005 Sub-decision (c).
    * ``schemas/orchestrator-event.yaml`` — the closed ``event_class``
      enum (lines 86-95) the per-class dispatch table covers; per-class
      branches (lines 113-416) define the fields the renderers read.

## ``find_repo_root()`` discipline (Epic 1 retro Action #1)

This module honors the discipline by construction: there is no
filesystem surface to compute (the appender consumes caller-supplied
``event_log_path``); ``find_repo_root()`` is NOT called anywhere in
this module under any code path.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any, TextIO

from loud_fail_harness.input_hardening import harden_path_segment

if TYPE_CHECKING:
    from loud_fail_harness.lifecycle_state_machine import EventLogAppender


def default_event_log_path(
    qa_evidence_root: pathlib.Path, story_id: str, run_id: str
) -> pathlib.Path:
    """Resolve the canonical events.jsonl path under qa-evidence.

    Returns ``qa_evidence_root / story_id / run_id / "events.jsonl"``
    — sibling to Story 2.6's per-specialist ``logs/`` directory at
    :data:`loud_fail_harness.specialist_dispatch.LOG_PATH_TEMPLATE`.
    Pure path resolution; no I/O; no directory creation (the appender
    creates the parent lazily on first write).

    Args:
        qa_evidence_root: Caller-supplied prefix; conventionally
            ``pathlib.Path("_bmad-output/qa-evidence")`` per
            architecture.md View 3 line 1171.
        story_id: BMAD story identifier (e.g. ``"sample-auto-001"``).
        run_id: Orchestrator-domain run identifier per ADR-005
            Consequence 1.

    Returns:
        :class:`pathlib.Path` pointing at the canonical events.jsonl
        location.

    Input-hardening (Story 24.2 — closes deferred-work ``default_event_log_path``
    ``story_id``/``run_id`` path-traversal): both segments are routed through
    :func:`~loud_fail_harness.input_hardening.harden_path_segment` so a hostile
    identifier cannot escape ``qa_evidence_root``.
    """
    harden_path_segment(story_id, "default_event_log_path.story_id")
    harden_path_segment(run_id, "default_event_log_path.run_id")
    return qa_evidence_root / story_id / run_id / "events.jsonl"


def _render_state_transition(event: dict[str, Any]) -> str:
    """Render a ``state-transition`` event's brief detail per AC-3."""
    return f"{event['from_state']} → {event['to_state']}"


def _render_state_transition_halted(event: dict[str, Any]) -> str:
    """Render a ``state-transition-halted`` event's brief detail per AC-3."""
    return f"halted at {event['halted_at_state']}: {event['halt_reason']}"


def _render_specialist_dispatched(event: dict[str, Any]) -> str:
    """Render a ``specialist-dispatched`` event's brief detail per AC-3."""
    return f"specialist={event['specialist']} attempt={event['retry_attempt']}"


def _render_specialist_returned(event: dict[str, Any]) -> str:
    """Render a ``specialist-returned`` event's brief detail per AC-3."""
    return f"specialist={event['specialist']} status={event['status']}"


#: Per-event-class dispatch table. Keys are the kebab-case event class
#: identifiers from ``schemas/orchestrator-event.yaml`` lines 86-95;
#: values are the per-class brief-detail renderers. Epic 6's Story 6.5
#: + 6.7 extend the table with marker-emission branches; existing
#: branches are NOT touched. Unknown event classes fall through to the
#: generic ``event_id`` fallback in :func:`format_event_for_stream`.
_BRIEF_DETAIL_RENDERERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "state-transition": _render_state_transition,
    "state-transition-halted": _render_state_transition_halted,
    "specialist-dispatched": _render_specialist_dispatched,
    "specialist-returned": _render_specialist_returned,
}


def _format_timestamp_short(timestamp: str) -> str:
    """Truncate an ISO-8601 timestamp to ``HH:MM:SS`` form.

    Sourced from the event's ``timestamp`` field (NOT from
    :func:`datetime.now`) per AC-3's purity contract — the function is
    deterministic given the same input event.

    Args:
        timestamp: ISO-8601 string from the event payload's
            ``timestamp`` field. Per ``schemas/orchestrator-event.yaml``
            line 105 ``format: date-time``, this is always a parseable
            ISO-8601 form.

    Returns:
        ``HH:MM:SS`` string in the timestamp's encoded timezone (which
        is UTC by Pattern 3 convention).
    """
    parsed = datetime.fromisoformat(timestamp)
    return parsed.strftime("%H:%M:%S")


def format_event_for_stream(event: dict[str, Any]) -> str:
    """Render a one-line streaming string from an orchestrator event.

    The format is ``<HH:MM:SS> [<event_class>] <brief_detail>`` per
    AC-3. The function is PURE — no I/O, no clock read, no module-level
    state mutation. Deterministic given the same input event.

    Args:
        event: Schema-valid orchestrator event dict per
            ``schemas/orchestrator-event.yaml``. The function trusts
            the dict is schema-valid (sensor-not-advisor; the upstream
            emitter validates).

    Returns:
        Single line (no trailing newline; the appender's job to add it)
        of the canonical streaming form.
    """
    event_class = event["event_class"]
    timestamp = _format_timestamp_short(event["timestamp"])
    renderer = _BRIEF_DETAIL_RENDERERS.get(event_class)
    if renderer is not None:
        brief = renderer(event)
    else:
        # Forward-compat fallback for unknown event classes (Epic 6+).
        # Renders the line; does NOT raise; the unknown class is
        # surfaced as a usable summary. Future stories extend the
        # dispatch table to give the class a richer per-class render.
        brief = event.get("event_id", "")
    return f"{timestamp} [{event_class}] {brief}"


def make_event_log_appender(
    event_log_path: pathlib.Path,
    *,
    stream: TextIO = sys.stdout,
    fsync: bool = True,
) -> EventLogAppender:
    """Construct an :data:`EventLogAppender` closure for per-event JSONL + stream.

    The returned closure performs two writes per invocation in this
    load-bearing order per AC-4:

        1. JSONL persistence FIRST — appends one
           ``json.dumps(event, ensure_ascii=False) + "\\n"`` line to
           ``event_log_path``; lazily creates the parent directory on
           the first call; calls :func:`os.fsync` after the write when
           ``fsync=True``.
        2. Terminal render SECOND —
           ``stream.write(format_event_for_stream(event) + "\\n")``
           followed by ``stream.flush()`` for immediate visibility.

    The ordering is the durability invariant per ADR-005 Sub-decision
    (c): a crash between the two writes leaves the events.jsonl line on
    disk (the canonical record Story 8.1 replays) even if the
    practitioner missed the terminal line.

    Pattern 5 loud-fail discipline: :exc:`OSError` from any of
    ``mkdir`` / ``open`` / ``write`` / ``fsync`` propagates unchanged
    to the caller; the closure does NOT catch, does NOT log-and-suppress,
    does NOT silently substitute a fallback path. A stream-write
    exception (e.g., :exc:`BrokenPipeError`) propagates AFTER the JSONL
    line is durable.

    Args:
        event_log_path: :class:`pathlib.Path` for the JSONL append
            target. Typically resolved via :func:`default_event_log_path`.
        stream: Caller-supplied :class:`TextIO` for the per-event
            terminal render. Defaults to :data:`sys.stdout` for the
            live-terminal posture; tests pass :class:`io.StringIO`.
        fsync: Whether to call :func:`os.fsync` after each JSONL write.
            Defaults to ``True`` for production durability; tests pass
            ``False`` for ``tmp_path`` speed.

    Returns:
        :data:`EventLogAppender` closure with signature
        ``(event: dict[str, Any]) -> None`` — structurally compatible
        with Story 2.4's
        :data:`loud_fail_harness.lifecycle_state_machine.EventLogAppender`
        type alias verbatim.
    """

    def appender(event: dict[str, Any]) -> None:
        # Durability invariant per AC-4: JSONL FIRST, terminal SECOND.
        # If the JSONL write raises, the terminal stream is UNTOUCHED
        # (the practitioner does NOT see "seam advanced" without a
        # durable record).
        event_log_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event, ensure_ascii=False)
        with open(event_log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
            if fsync:
                os.fsync(f.fileno())

        # Terminal render SECOND. A stream-write exception propagates
        # AFTER the JSONL line is durable.
        stream.write(format_event_for_stream(event) + "\n")
        stream.flush()

    return appender


__all__ = [
    "default_event_log_path",
    "format_event_for_stream",
    "make_event_log_appender",
]
