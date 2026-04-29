"""Contract-coverage matrix for the per-seam state-streaming substrate
library (story 2.12).

This docstring IS the contract-coverage checklist required by AC-7's
multi-event integration test plus the AC-1 / AC-2 / AC-3 / AC-4 unit
tests. Reviewers verify every row maps to at least one passing test in
this module. The matrix is review-enforced, NOT CI-enforced (parallel
to 1.2 / 2.2 / 2.3 / 2.4 / 2.5 / 2.6 / 2.11 AC discipline).

AC-1 module-shape:
    [x] module exposes the three public functions
        → test_module_exposes_public_api[*]
    [x] module-level docstring documents substrate-library identity
        → test_module_docstring_documents_substrate_library_identity
    [x] no module top-level find_repo_root() call
        → test_no_module_top_level_find_repo_root_call
    [x] __all__ enumerates documented exports
        → test_all_enumerates_documented_exports

AC-2 path conformance + JSONL persistence:
    [x] default_event_log_path resolves to the canonical form
        → test_default_event_log_path_resolves_to_canonical_form
    [x] appender creates parent dir lazily
        → test_appender_creates_parent_dir_lazily
    [x] appender writes one JSONL line per event
        → test_appender_writes_one_jsonl_line_per_event
    [x] appender propagates OSError on fsync failure
        → test_appender_propagates_oserror_on_fsync_failure
    [x] file is UTF-8 / LF / no BOM
        → test_appender_writes_utf8_lf_without_bom
    [x] fsync=False skips os.fsync
        → test_appender_skips_fsync_when_disabled

AC-3 streaming format:
    [x] specialist-dispatched canonical render
        → test_format_specialist_dispatched_renders_canonical_form
    [x] specialist-returned canonical render
        → test_format_specialist_returned_renders_canonical_form
    [x] state-transition uses U+2192 arrow
        → test_format_state_transition_renders_with_arrow
    [x] state-transition-halted renders halt_reason
        → test_format_state_transition_halted_renders_with_halt_reason
    [x] unknown event class falls back gracefully
        → test_format_unknown_event_class_falls_back_gracefully
    [x] format function is pure (deterministic)
        → test_format_event_for_stream_is_pure
    [x] timestamp comes from event payload, NOT clock
        → test_format_uses_event_timestamp_not_now

AC-4 combined behavior:
    [x] appender writes JSONL, then streams
        → test_appender_writes_jsonl_then_streams
    [x] JSONL persistence happens BEFORE terminal render (ordering)
        → test_appender_persists_before_streaming
    [x] closure signature matches EventLogAppender alias
        → test_appender_signature_matches_event_log_appender_alias
    [x] stream is flushed after each write
        → test_appender_flushes_stream_after_write

AC-7 multi-event integration test:
    [x] full Epic-2-era 10-event sequence flows through one appender
        → test_full_epic_2_era_lifecycle_sequence_through_single_appender
"""

from __future__ import annotations

import inspect
import io
import json
import pathlib
from typing import Any
from unittest import mock

import pytest

from loud_fail_harness.event_streaming import (
    default_event_log_path,
    format_event_for_stream,
    make_event_log_appender,
)


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #


@pytest.fixture
def captured_stream() -> io.StringIO:
    """Per-test stream capture (parallel to existing test_specialist_dispatch
    fixture style)."""
    return io.StringIO()


@pytest.fixture
def event_log_path(tmp_path: pathlib.Path) -> pathlib.Path:
    """Canonical events.jsonl path under a tmp_path-rooted qa-evidence."""
    return tmp_path / "qa-evidence" / "sample-auto-001" / "test-run-id" / "events.jsonl"


def _make_state_transition_event(
    *,
    from_state: str,
    to_state: str,
    timestamp: str = "2026-04-29T12:00:00+00:00",
    event_id: str = "ev-test-st-0001",
    story_id: str = "sample-auto-001",
) -> dict[str, Any]:
    """Hand-author a state-transition event matching
    ``schemas/orchestrator-event.yaml`` lines 178-210."""
    return {
        "event_class": "state-transition",
        "event_id": event_id,
        "timestamp": timestamp,
        "story_id": story_id,
        "from_state": from_state,
        "to_state": to_state,
    }


def _make_specialist_dispatched_event(
    *,
    specialist: str,
    timestamp: str = "2026-04-29T12:00:00+00:00",
    event_id: str = "ev-test-sd-0001",
    story_id: str = "sample-auto-001",
    retry_attempt: int = 0,
) -> dict[str, Any]:
    """Hand-author a specialist-dispatched event matching
    ``schemas/orchestrator-event.yaml`` lines 113-143."""
    return {
        "event_class": "specialist-dispatched",
        "event_id": event_id,
        "timestamp": timestamp,
        "story_id": story_id,
        "specialist": specialist,
        "prompt_id": f"prompt-{specialist}-{retry_attempt}",
        "retry_attempt": retry_attempt,
    }


def _make_specialist_returned_event(
    *,
    specialist: str,
    status: str,
    timestamp: str = "2026-04-29T12:00:00+00:00",
    event_id: str = "ev-test-sr-0001",
    story_id: str = "sample-auto-001",
    retry_attempt: int = 0,
) -> dict[str, Any]:
    """Hand-author a specialist-returned event matching
    ``schemas/orchestrator-event.yaml`` lines 144-176."""
    return {
        "event_class": "specialist-returned",
        "event_id": event_id,
        "timestamp": timestamp,
        "story_id": story_id,
        "specialist": specialist,
        "prompt_id": f"prompt-{specialist}-{retry_attempt}",
        "retry_attempt": retry_attempt,
        "status": status,
    }


def _make_state_transition_halted_event(
    *,
    halted_at_state: str,
    halt_reason: str,
    timestamp: str = "2026-04-29T12:00:00+00:00",
    event_id: str = "ev-test-sth-0001",
    story_id: str = "sample-auto-001",
) -> dict[str, Any]:
    """Hand-author a state-transition-halted event matching
    ``schemas/orchestrator-event.yaml`` lines 211-243."""
    return {
        "event_class": "state-transition-halted",
        "event_id": event_id,
        "timestamp": timestamp,
        "story_id": story_id,
        "halted_at_state": halted_at_state,
        "halt_reason": halt_reason,
    }


# --------------------------------------------------------------------------- #
# AC-1 module-shape tests                                                     #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "name",
    [
        "default_event_log_path",
        "format_event_for_stream",
        "make_event_log_appender",
    ],
)
def test_module_exposes_public_api(name: str) -> None:
    """AC-1: the three public symbols are importable from the module.

    The ``EventLogAppender`` type alias is canonically owned by
    ``lifecycle_state_machine`` per Story 2.4; this module does NOT
    redefine or re-export it (AC-1 paragraph (d), AC-4, Do-Not-Do
    matrix row 2).
    """
    import loud_fail_harness.event_streaming as mod

    assert hasattr(mod, name), f"event_streaming must export {name!r}"


def test_module_does_not_redefine_event_log_appender_alias() -> None:
    """AC-1 + AC-4 + Do-Not-Do row 2: ``EventLogAppender`` is NOT redefined here.

    The single canonical alias lives at
    ``loud_fail_harness.lifecycle_state_machine.EventLogAppender``
    (Story 2.4 line 309). Re-defining it in this module would create
    import ambiguity for downstream readers.
    """
    import loud_fail_harness.event_streaming as mod

    assert "EventLogAppender" not in mod.__dict__, (
        "event_streaming.py must NOT define a module-level "
        "EventLogAppender attribute (AC-1 / AC-4 / Do-Not-Do row 2)"
    )
    assert "EventLogAppender" not in mod.__all__, (
        "event_streaming.py must NOT export EventLogAppender via __all__"
    )


def test_module_docstring_documents_substrate_library_identity() -> None:
    """AC-1: the module docstring names the substrate-library identity."""
    import loud_fail_harness.event_streaming as mod

    assert mod.__doc__ is not None
    assert "substrate-library identity" in mod.__doc__ or (
        "substrate library" in mod.__doc__ and "NOT a sixth substrate component" in mod.__doc__
    ), (
        "module docstring must name the substrate-library identity per AC-1 + ADR-003"
    )


def test_no_module_top_level_find_repo_root_call() -> None:
    """AC-1 + Epic 1 retro Action #1: no find_repo_root() invocation in code.

    The substrate's path-resolution surface is caller-supplied via the
    ``event_log_path`` parameter; calling ``find_repo_root()`` at module
    import time would raise ``RuntimeError`` in alien environments.
    The check parses the AST and walks for ``Call`` nodes whose target
    is the ``find_repo_root`` name — docstring mentions of the policy
    name are permitted (the module DOES discuss the discipline in its
    docstring), only actual invocations are forbidden.
    """
    import ast

    import loud_fail_harness.event_streaming as mod

    tree = ast.parse(inspect.getsource(mod))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = (
                func.id
                if isinstance(func, ast.Name)
                else (func.attr if isinstance(func, ast.Attribute) else None)
            )
            assert name != "find_repo_root", (
                "event_streaming.py must NOT call find_repo_root() at any code path "
                "(Epic 1 retro Action #1)"
            )
    # Also verify the module does NOT import the symbol.
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                assert alias.name != "find_repo_root", (
                    "event_streaming.py must NOT import find_repo_root() "
                    "(Epic 1 retro Action #1)"
                )


def test_all_enumerates_documented_exports() -> None:
    """AC-1: ``__all__`` enumerates the three public symbols.

    ``EventLogAppender`` is intentionally absent — the canonical alias
    lives in ``lifecycle_state_machine`` per Story 2.4 and the
    Do-Not-Do matrix forbids redefining it here.
    """
    import loud_fail_harness.event_streaming as mod

    assert set(mod.__all__) == {
        "default_event_log_path",
        "format_event_for_stream",
        "make_event_log_appender",
    }


# --------------------------------------------------------------------------- #
# AC-2 path conformance + JSONL persistence tests                             #
# --------------------------------------------------------------------------- #


def test_default_event_log_path_resolves_to_canonical_form() -> None:
    """AC-2: ``default_event_log_path`` returns the canonical events.jsonl path."""
    resolved = default_event_log_path(
        pathlib.Path("/tmp/qa-evidence"), "sample-auto-001", "20260429T120000Z"
    )
    assert resolved == pathlib.Path(
        "/tmp/qa-evidence/sample-auto-001/20260429T120000Z/events.jsonl"
    )


def test_appender_creates_parent_dir_lazily(
    event_log_path: pathlib.Path, captured_stream: io.StringIO
) -> None:
    """AC-2: the appender lazily creates ``event_log_path.parent`` on first call."""
    assert not event_log_path.parent.exists(), (
        "preconditions: parent dir does NOT exist before the appender runs"
    )
    appender = make_event_log_appender(event_log_path, stream=captured_stream, fsync=False)
    appender(_make_state_transition_event(from_state="ready-for-dev", to_state="in-progress"))
    assert event_log_path.parent.is_dir(), "appender must create parent dir lazily"
    assert event_log_path.exists(), "appender must write the events.jsonl file"


def test_appender_writes_one_jsonl_line_per_event(
    event_log_path: pathlib.Path, captured_stream: io.StringIO
) -> None:
    """AC-2: each invocation appends exactly one JSONL line."""
    appender = make_event_log_appender(event_log_path, stream=captured_stream, fsync=False)
    e1 = _make_state_transition_event(
        from_state="ready-for-dev", to_state="in-progress", event_id="ev-1"
    )
    e2 = _make_specialist_dispatched_event(specialist="dev", event_id="ev-2")
    e3 = _make_specialist_returned_event(
        specialist="dev", status="pass", event_id="ev-3"
    )
    appender(e1)
    appender(e2)
    appender(e3)

    lines = event_log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    parsed = [json.loads(line) for line in lines]
    assert parsed[0] == e1
    assert parsed[1] == e2
    assert parsed[2] == e3


def test_appender_propagates_oserror_on_fsync_failure(
    event_log_path: pathlib.Path, captured_stream: io.StringIO
) -> None:
    """AC-2 + Pattern 5: ``OSError`` from ``os.fsync`` propagates unchanged."""
    appender = make_event_log_appender(event_log_path, stream=captured_stream, fsync=True)
    with mock.patch(
        "loud_fail_harness.event_streaming.os.fsync",
        side_effect=OSError("simulated fsync failure"),
    ):
        with pytest.raises(OSError, match="simulated fsync failure"):
            appender(
                _make_state_transition_event(
                    from_state="ready-for-dev", to_state="in-progress"
                )
            )


def test_appender_writes_utf8_lf_without_bom(
    event_log_path: pathlib.Path, captured_stream: io.StringIO
) -> None:
    """AC-2: the events.jsonl file is UTF-8, LF line endings, no BOM."""
    appender = make_event_log_appender(event_log_path, stream=captured_stream, fsync=False)
    appender(
        _make_state_transition_event(from_state="ready-for-dev", to_state="in-progress")
    )
    raw = event_log_path.read_bytes()
    # UTF-8 BOM is b"\xef\xbb\xbf"; assert absent.
    assert not raw.startswith(b"\xef\xbb\xbf"), "events.jsonl must NOT carry a UTF-8 BOM"
    # LF terminator (no CRLF anywhere).
    assert b"\r" not in raw, "events.jsonl must use LF, not CRLF"
    assert raw.endswith(b"\n"), "events.jsonl line must terminate with LF"


def test_appender_skips_fsync_when_disabled(
    event_log_path: pathlib.Path, captured_stream: io.StringIO
) -> None:
    """AC-2: ``fsync=False`` skips the ``os.fsync`` call (tmp_path speed posture)."""
    appender = make_event_log_appender(event_log_path, stream=captured_stream, fsync=False)
    with mock.patch("loud_fail_harness.event_streaming.os.fsync") as mocked_fsync:
        appender(
            _make_state_transition_event(
                from_state="ready-for-dev", to_state="in-progress"
            )
        )
    mocked_fsync.assert_not_called()


# --------------------------------------------------------------------------- #
# AC-3 streaming format tests                                                 #
# --------------------------------------------------------------------------- #


def test_format_specialist_dispatched_renders_canonical_form() -> None:
    """AC-3: specialist-dispatched renders ``HH:MM:SS [specialist-dispatched] specialist=<n> attempt=<n>``."""
    event = _make_specialist_dispatched_event(
        specialist="dev",
        retry_attempt=0,
        timestamp="2026-04-29T12:00:00+00:00",
    )
    rendered = format_event_for_stream(event)
    assert rendered == "12:00:00 [specialist-dispatched] specialist=dev attempt=0"


def test_format_specialist_returned_renders_canonical_form() -> None:
    """AC-3: specialist-returned renders ``HH:MM:SS [specialist-returned] specialist=<n> status=<s>``."""
    event = _make_specialist_returned_event(
        specialist="qa",
        status="pass",
        timestamp="2026-04-29T12:30:45+00:00",
    )
    rendered = format_event_for_stream(event)
    assert rendered == "12:30:45 [specialist-returned] specialist=qa status=pass"


def test_format_state_transition_renders_with_arrow() -> None:
    """AC-3: state-transition uses the U+2192 RIGHTWARDS ARROW character."""
    event = _make_state_transition_event(
        from_state="ready-for-dev",
        to_state="in-progress",
        timestamp="2026-04-29T12:00:00+00:00",
    )
    rendered = format_event_for_stream(event)
    assert rendered.startswith("12:00:00 [state-transition]")
    assert "ready-for-dev → in-progress" in rendered  # noqa: RUF001 — U+2192 arrow is intentional
    # Defensive: the arrow IS the U+2192 RIGHTWARDS ARROW codepoint.
    assert "→" in rendered


def test_format_state_transition_halted_renders_with_halt_reason() -> None:
    """AC-3: state-transition-halted renders ``halted at <state>: <reason>``."""
    event = _make_state_transition_halted_event(
        halted_at_state="review",
        halt_reason="non-pass-envelope",
        timestamp="2026-04-29T13:00:00+00:00",
    )
    rendered = format_event_for_stream(event)
    assert rendered == "13:00:00 [state-transition-halted] halted at review: non-pass-envelope"


def test_format_unknown_event_class_falls_back_gracefully() -> None:
    """AC-3 forward-compat: unknown event_class falls back to ``[<class>] <event_id>``.

    Per the verbatim epic AC at epics.md Story 2.12 lines 1551-1553,
    Epic 2's basic streaming does NOT include marker emissions beyond
    what Story 2.6 emits structurally; Epic 6's Story 6.5 + 6.7 thicken
    the streaming format by ADDING new dispatch-table branches for
    cost-event / cost-near-ceiling / specialist-timeout. THIS test
    proves the fallback renders the unknown class — does NOT raise —
    so Epic 6's wiring is purely additive.
    """
    event = {
        "event_class": "cost-event",
        "event_id": "ev-test-cost-deadbeef",
        "timestamp": "2026-04-29T14:00:00+00:00",
        "story_id": "sample-auto-001",
        "prompt_id": "p-1",
        "retry_attempt": 0,
        "specialist": "dev",
        "cost_delta_usd": 0.42,
    }
    rendered = format_event_for_stream(event)
    assert rendered == "14:00:00 [cost-event] ev-test-cost-deadbeef"


def test_format_event_for_stream_is_pure() -> None:
    """AC-3: ``format_event_for_stream`` is deterministic given the same input."""
    event = _make_state_transition_event(
        from_state="ready-for-dev", to_state="in-progress"
    )
    first = format_event_for_stream(event)
    second = format_event_for_stream(event)
    assert first == second, "format_event_for_stream must be deterministic"


def test_format_uses_event_timestamp_not_now() -> None:
    """AC-3: the rendered timestamp comes from the event's ``timestamp`` field.

    Constructs an event with a past timestamp; asserts the rendered
    prefix matches the past time, NOT the current time. Proves the
    function does NOT call ``datetime.now()``.
    """
    event = _make_state_transition_event(
        from_state="ready-for-dev",
        to_state="in-progress",
        timestamp="2020-01-01T00:00:00+00:00",
    )
    rendered = format_event_for_stream(event)
    assert rendered.startswith("00:00:00 [")


# --------------------------------------------------------------------------- #
# AC-4 combined behavior tests                                                #
# --------------------------------------------------------------------------- #


def test_appender_writes_jsonl_then_streams(
    event_log_path: pathlib.Path, captured_stream: io.StringIO
) -> None:
    """AC-4: both writes succeed; JSONL contains the event, stream contains the format."""
    appender = make_event_log_appender(event_log_path, stream=captured_stream, fsync=False)
    event = _make_state_transition_event(
        from_state="ready-for-dev", to_state="in-progress"
    )
    appender(event)

    # JSONL file populated.
    body = json.loads(event_log_path.read_text(encoding="utf-8").rstrip("\n"))
    assert body == event
    # Stream populated with the AC-3 render + trailing newline.
    streamed = captured_stream.getvalue()
    assert streamed.endswith("\n")
    assert streamed.rstrip("\n") == format_event_for_stream(event)


def test_appender_persists_before_streaming(
    event_log_path: pathlib.Path, captured_stream: io.StringIO
) -> None:
    """AC-4 durability invariant: JSONL FIRST / terminal SECOND.

    If the JSONL ``open`` raises, the terminal stream MUST be untouched
    (the practitioner does NOT see "seam advanced" without a durable
    record).
    """
    appender = make_event_log_appender(event_log_path, stream=captured_stream, fsync=False)
    # Patch open to raise on the JSONL append — the parent mkdir runs
    # FIRST so the directory may exist after the call; what matters is
    # that the stream is UNTOUCHED.
    with mock.patch(
        "loud_fail_harness.event_streaming.open",
        side_effect=OSError("simulated open failure"),
    ):
        with pytest.raises(OSError, match="simulated open failure"):
            appender(
                _make_state_transition_event(
                    from_state="ready-for-dev", to_state="in-progress"
                )
            )
    assert captured_stream.getvalue() == "", (
        "stream must be UNTOUCHED when JSONL persistence fails (AC-4 ordering invariant)"
    )


def test_appender_propagates_broken_pipe_after_jsonl_durable(
    event_log_path: pathlib.Path,
) -> None:
    """Story 2.12 review patch: ``BrokenPipeError`` propagates per Pattern 5.

    The decision (review 2026-04-29 decision-needed #1): when the
    terminal stream raises (e.g. stdout pipe consumer exits — practitioner
    closed the terminal), the appender propagates per Pattern 5 — does
    NOT silently absorb. The durability contract is still honored:
    AC-4's load-bearing ordering means the JSONL line is on disk
    BEFORE the propagation, so Story 8.1's recovery-replay machinery
    has the canonical record even though the terminal line was lost.
    """

    class BrokenPipeStream(io.StringIO):
        def write(self, s: str) -> int:  # type: ignore[override]
            raise BrokenPipeError("simulated stdout pipe closed")

    stream = BrokenPipeStream()
    appender = make_event_log_appender(event_log_path, stream=stream, fsync=False)
    event = _make_state_transition_event(
        from_state="ready-for-dev", to_state="in-progress"
    )

    with pytest.raises(BrokenPipeError, match="simulated stdout pipe closed"):
        appender(event)

    # JSONL is durable BEFORE the BrokenPipeError propagates: the
    # canonical record is on disk for ADR-005 Sub-decision (c) replay.
    persisted = event_log_path.read_text(encoding="utf-8").splitlines()
    assert len(persisted) == 1
    assert json.loads(persisted[0]) == event


def test_appender_signature_matches_event_log_appender_alias(
    event_log_path: pathlib.Path, captured_stream: io.StringIO
) -> None:
    """AC-4: the closure's signature is ``(event: dict[str, Any]) -> None``."""
    appender = make_event_log_appender(event_log_path, stream=captured_stream, fsync=False)
    sig = inspect.signature(appender)
    params = list(sig.parameters.values())
    assert len(params) == 1, "appender must accept exactly one positional argument"
    # The closure annotates `event: dict[str, Any]` — assert presence.
    assert params[0].name == "event"
    # Cannot use isinstance against Callable alias; the structural
    # contract is the signature shape above.


def test_appender_flushes_stream_after_write(
    event_log_path: pathlib.Path,
) -> None:
    """AC-4: ``stream.flush()`` is called after the write so the line surfaces immediately."""
    flushed = {"count": 0}

    class FlushTrackingStream(io.StringIO):
        def flush(self) -> None:  # type: ignore[override]
            flushed["count"] += 1
            super().flush()

    stream = FlushTrackingStream()
    appender = make_event_log_appender(event_log_path, stream=stream, fsync=False)
    appender(_make_state_transition_event(from_state="ready-for-dev", to_state="in-progress"))
    assert flushed["count"] >= 1, "stream.flush() must be called at least once after the write"


# --------------------------------------------------------------------------- #
# AC-7 multi-event integration test                                           #
# --------------------------------------------------------------------------- #


def test_full_epic_2_era_lifecycle_sequence_through_single_appender(
    event_log_path: pathlib.Path, captured_stream: io.StringIO
) -> None:
    """AC-7: the full Epic-2-era ten-event sequence flows through one appender.

    Sequence (per epics.md Story 2.4 lifecycle map +
    ``lifecycle_state_machine.py`` ``LIFECYCLE_TRANSITIONS`` lines
    285-290 + Story 2.6's two-event-per-dispatch pattern):

        1.  state-transition (ready-for-dev → in-progress)
        2.  specialist-dispatched (dev, attempt=0)
        3.  specialist-returned (dev, status=pass)
        4.  state-transition (in-progress → review)
        5.  specialist-dispatched (review-bmad, attempt=0)
        6.  specialist-returned (review-bmad, status=pass)
        7.  state-transition (review → qa)
        8.  specialist-dispatched (qa, attempt=0)
        9.  specialist-returned (qa, status=pass)
        10. state-transition (qa → done)

    Asserts the events.jsonl file contains exactly TEN lines in the
    documented order; asserts the captured stream contains exactly TEN
    lines in the same order with the AC-3 streaming format applied.
    Proves AC-1 + AC-2 + AC-3 + AC-4 compose correctly.
    """
    appender = make_event_log_appender(event_log_path, stream=captured_stream, fsync=False)

    sequence: list[dict[str, Any]] = [
        _make_state_transition_event(
            from_state="ready-for-dev",
            to_state="in-progress",
            event_id="ev-1",
            timestamp="2026-04-29T12:00:00+00:00",
        ),
        _make_specialist_dispatched_event(
            specialist="dev",
            event_id="ev-2",
            timestamp="2026-04-29T12:00:01+00:00",
        ),
        _make_specialist_returned_event(
            specialist="dev",
            status="pass",
            event_id="ev-3",
            timestamp="2026-04-29T12:01:30+00:00",
        ),
        _make_state_transition_event(
            from_state="in-progress",
            to_state="review",
            event_id="ev-4",
            timestamp="2026-04-29T12:01:31+00:00",
        ),
        _make_specialist_dispatched_event(
            specialist="review-bmad",
            event_id="ev-5",
            timestamp="2026-04-29T12:01:32+00:00",
        ),
        _make_specialist_returned_event(
            specialist="review-bmad",
            status="pass",
            event_id="ev-6",
            timestamp="2026-04-29T12:02:45+00:00",
        ),
        _make_state_transition_event(
            from_state="review",
            to_state="qa",
            event_id="ev-7",
            timestamp="2026-04-29T12:02:46+00:00",
        ),
        _make_specialist_dispatched_event(
            specialist="qa",
            event_id="ev-8",
            timestamp="2026-04-29T12:02:47+00:00",
        ),
        _make_specialist_returned_event(
            specialist="qa",
            status="pass",
            event_id="ev-9",
            timestamp="2026-04-29T12:04:00+00:00",
        ),
        _make_state_transition_event(
            from_state="qa",
            to_state="done",
            event_id="ev-10",
            timestamp="2026-04-29T12:04:01+00:00",
        ),
    ]

    for event in sequence:
        appender(event)

    # JSONL: exactly ten lines, each roundtrips to the emitted event.
    persisted_lines = event_log_path.read_text(encoding="utf-8").splitlines()
    assert len(persisted_lines) == 10
    persisted_events = [json.loads(line) for line in persisted_lines]
    assert persisted_events == sequence

    # Stream: exactly ten lines, hand-authored verbatim per AC-3 +
    # AC-4. Hand-authoring (NOT computed via ``format_event_for_stream``)
    # means a regression in any per-class renderer is caught by this
    # integration test — the previous self-comparison form
    # (``expected = [format_event_for_stream(e) for e in sequence]``)
    # was circular and would mask renderer regressions.
    expected_stream_lines = [
        "12:00:00 [state-transition] ready-for-dev → in-progress",  # noqa: RUF001
        "12:00:01 [specialist-dispatched] specialist=dev attempt=0",
        "12:01:30 [specialist-returned] specialist=dev status=pass",
        "12:01:31 [state-transition] in-progress → review",  # noqa: RUF001
        "12:01:32 [specialist-dispatched] specialist=review-bmad attempt=0",
        "12:02:45 [specialist-returned] specialist=review-bmad status=pass",
        "12:02:46 [state-transition] review → qa",  # noqa: RUF001
        "12:02:47 [specialist-dispatched] specialist=qa attempt=0",
        "12:04:00 [specialist-returned] specialist=qa status=pass",
        "12:04:01 [state-transition] qa → done",  # noqa: RUF001
    ]
    streamed_lines = captured_stream.getvalue().splitlines()
    assert streamed_lines == expected_stream_lines

    # Parent dir was lazily created.
    assert event_log_path.parent.is_dir()
