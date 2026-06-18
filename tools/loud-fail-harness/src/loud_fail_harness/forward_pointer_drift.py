"""Forward-pointer-drift parsers — Story 22.4 (H6 conditional landing).

The substrate half of the unified forward-pointer-drift gate. This module
holds the two pure parsers + the harness-level error; the rule evaluation +
CLI live in the sibling :mod:`forward_pointer_drift_gate` (the gate-shape
mirror of :mod:`no_destructive_resume_lint` / :mod:`done_story_review_ledger`).

## What this codifies (H6)

Planning/spec/retro docs carry **forward-pointers** — prose declaring that a
codification, status, or carry will land *later*. When the pointed-at work
lands, someone must manually **flip** the source pointer ("carries to …" →
"LANDED"). **Drift** is the failure mode: the target lands but the pointer is
never flipped (a stale "carries to <story>" pointing at a `done` story). H6
proposes a unified gate that detects this structurally. The Phase 1.5 retro
armed it on a 5+-flip trigger; the Phase-2 survey (Epics 14–19) counted six
flips (maintainer-ratified `triggered`, 2026-06-18), so the gate lands.

## Why bound targets, not prose inference

A fully-general NLP parse of arbitrary prose forward-pointers is infeasible
for a *deterministic* gate (the `fiberplane/drift` / VeriContext lesson —
doc-drift gates need machine-checkable bindings, not prose inference). The
`deferred-work.md` carry surface references targets mostly at *phase* level
("carries to Phase 3") or as *soft suggestions* ("Story X is the natural
resolution point") — neither is a story-key binding. So this parser recognizes
forward-pointers from exactly two machine-checkable surfaces (maintainer-
ratified scope, Story 22.4 AC-2):

* **Structured annotation** (the forward-going, future-proof form):
  ``<!-- forward-pointer: target=<story-key>; status=pending -->``. Pointers
  authored this way are machine-checkable by construction.
* **Conservative inline carry-binding** (over the existing prose surface): a
  CLOSED set of explicit hard-binding verbs immediately followed by a
  hyphenated story-key token — ``deferred to <key>`` / ``carries to <key>`` /
  ``lands in <key>`` / ``resolved by <key>`` / ``trigger-armed for <key>``.
  Phase-level pointers ("carries to Phase 3") and soft suggestions ("Story X
  is the natural resolution point") deliberately do NOT match — they carry no
  resolvable story-key, so inferring a target from them would manufacture
  false positives.

A malformed / unreadable input is a harness-level error (exit-2 class via the
gate), never a silent empty set (loud-fail doctrine).
"""

from __future__ import annotations

import re
from typing import Final, NamedTuple

import yaml

__all__ = [
    "KNOWN_FLIPPED_STATUSES",
    "PENDING_STATUSES",
    "CarryPointer",
    "ForwardPointerDriftError",
    "iter_carry_pointers",
    "iter_done_story_keys",
    "resolve_done_target",
]

#: Story-vs-epic-vs-retro discrimination — identical to Story 24.3's
#: :data:`done_story_review_ledger._STORY_KEY_RE`. Matches ``18-3-…`` and
#: alpha-suffix keys ``1-10a-…`` but not ``epic-18`` / project-metadata keys.
_STORY_KEY_RE: Final[re.Pattern[str]] = re.compile(r"^\d+-\d+[a-z]?-")

#: A target token in a forward-pointer: a story-key PREFIX (``18-3`` / ``1-10a``)
#: or a full key (``18-3-concurrent-env-…``). Resolution against the live
#: ``done`` set is prefix-aware (see :func:`resolve_done_target`), so authors
#: may write the short ``18-3`` form and still bind the full done key.
_TARGET_TOKEN: Final[str] = r"\d+-\d+[a-z]?(?:-[a-z0-9-]+)?"

#: The forward-going structured annotation. ``target`` + ``status`` are the
#: machine-checkable binding (the fiberplane/drift embedded-marker lesson).
_ANNOTATION_RE: Final[re.Pattern[str]] = re.compile(
    r"<!--\s*forward-pointer:\s*"
    r"target=(?P<target>[^;>\s]+)\s*;\s*"
    r"status=\s*(?P<status>[^;>\s]+)\s*-->",
    re.IGNORECASE,
)

#: CLOSED set of explicit hard-binding verbs for the inline carry-binding
#: surface. Soft verbs ("natural resolution point", "will exercise", "route
#: to") are intentionally excluded — they are suggestions, not bindings.
#: The leading ``\b`` prevents embedded matches (e.g. "undeferred to X" must
#: not fire on the "deferred to" substring).
_INLINE_BINDING_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?P<phrase>deferred to|carries to|carry to|lands in|resolved by|"
    r"trigger-armed for|trigger armed for)\s+(?:story\s+)?"
    r"(?P<target>" + _TARGET_TOKEN + r")",
    re.IGNORECASE,
)

#: Annotation ``status`` values that mark a pointer as STILL-pending (the flip
#: was not performed). A ``status=landed`` / ``status=retired`` annotation is
#: the flipped state and does NOT fire. Inline carry-bindings are pending by
#: construction (they live in a deferred-work carry ledger).
PENDING_STATUSES: Final[frozenset[str]] = frozenset(
    {"pending", "carries", "carry", "armed", "open", "deferred"}
)

#: Annotation ``status`` values that mark a pointer as already-flipped (the
#: flip WAS performed). These are silently skipped — not drift. Any status
#: not in :data:`PENDING_STATUSES` or here is a loud-fail error (P5).
KNOWN_FLIPPED_STATUSES: Final[frozenset[str]] = frozenset(
    {"landed", "retired", "done", "closed", "resolved"}
)


class ForwardPointerDriftError(Exception):
    """Raised on substrate-level failures parsing the inputs (Pattern 5).

    Loud-fail / named-invariant convention — analogous in shape to
    :class:`done_story_review_ledger.DoneStoryReviewLedgerError`. A malformed
    or structurally-wrong sprint-status is a harness-level error (the gate
    maps it to exit 2), never a silent empty done-set.

    Attributes:
        reason: Short kebab-case discriminator naming the failure.
        diagnostic: Human-readable diagnostic + remediation hint (NFR-O5).
    """

    def __init__(self, *, reason: str, diagnostic: str) -> None:
        self.reason = reason
        self.diagnostic = diagnostic
        super().__init__(f"ForwardPointerDriftError[{reason}]: {diagnostic}")


class CarryPointer(NamedTuple):
    """A single parsed forward-pointer from the carry surface.

    A lightweight internal parse-result value object (NOT a Pydantic
    BaseModel ingress surface — its fields are display-only diagnostic text,
    not identifier/path ingress, so the input-hardening gate's
    model-classification does not govern it; mirrors
    :class:`done_story_review_ledger.ReviewLedgerItem`). Immutable by
    construction.

    Attributes:
        line_number: 1-indexed line the pointer was parsed from.
        target_key: The story-key (prefix or full) the pointer binds to.
        status: The pending-status token (``"carries"`` for inline bindings;
            the annotation's literal ``status=`` value otherwise).
        source_kind: ``"annotation"`` or ``"inline"`` — which surface matched.
        line_text: The original source line, for the diagnostic.
    """

    line_number: int
    target_key: str
    status: str
    source_kind: str
    line_text: str


def iter_done_story_keys(sprint_status_text: str) -> list[str]:
    """Yield the story keys whose ``development_status`` value is ``"done"``.

    Identical discrimination to Story 24.3: filters to keys matching
    :data:`_STORY_KEY_RE` so ``epic-N`` / ``epic-N-retrospective`` /
    project-metadata keys are excluded. Order follows the mapping's declared
    order. Raises :class:`ForwardPointerDriftError` on a malformed /
    structurally-wrong sprint-status — never a silent empty set (loud-fail).
    """
    try:
        raw = yaml.safe_load(sprint_status_text)
    except yaml.YAMLError as exc:
        raise ForwardPointerDriftError(
            reason="sprint-status-not-valid-yaml",
            diagnostic=f"sprint-status is not valid YAML: {exc}",
        ) from exc
    if not isinstance(raw, dict):
        raise ForwardPointerDriftError(
            reason="sprint-status-not-a-mapping",
            diagnostic="sprint-status did not parse to a mapping; expected a "
            "top-level mapping with a `development_status:` key",
        )
    development_status = raw.get("development_status")
    if development_status is None:
        if "development_status" not in raw:
            raise ForwardPointerDriftError(
                reason="development-status-missing",
                diagnostic="sprint-status has no `development_status:` key; "
                "cannot enumerate `done` stories",
            )
        raise ForwardPointerDriftError(
            reason="development-status-null",
            diagnostic="sprint-status `development_status:` key is null; "
            "cannot enumerate `done` stories",
        )
    if not isinstance(development_status, dict):
        raise ForwardPointerDriftError(
            reason="development-status-not-a-mapping",
            diagnostic="sprint-status `development_status:` is not a mapping; "
            "cannot enumerate `done` stories",
        )
    done_keys: list[str] = []
    for key, value in development_status.items():
        if not isinstance(key, str):
            continue
        if not isinstance(value, str):
            raise ForwardPointerDriftError(
                reason="non-scalar-status-value",
                diagnostic=f"sprint-status `development_status[{key!r}]` has a "
                f"non-string value ({type(value).__name__}); expected a status "
                "string like 'done'/'review'/'backlog'",
            )
        if value == "done" and _STORY_KEY_RE.match(key):
            done_keys.append(key)
    return done_keys


def iter_carry_pointers(carry_surface_text: str) -> list[CarryPointer]:
    """Extract every machine-checkable forward-pointer from the carry surface.

    Recognizes the two ratified surfaces (Story 22.4 AC-2): the structured
    ``<!-- forward-pointer: target=…; status=… -->`` annotation and the
    closed-set inline carry-binding verbs. Parsing is line-by-line (the carry
    surface is ~1 K lines / ~300 KB — never loaded whole into a regex with
    backtracking). A line may carry at most one annotation and multiple inline
    bindings; all are emitted. Annotation ``target`` is lowercased before
    comparison (case-insensitive binding). Annotation ``status`` must be in
    :data:`PENDING_STATUSES` (pending — emitted) or :data:`KNOWN_FLIPPED_STATUSES`
    (already-flipped — silently skipped); any other value is a loud-fail error.
    """
    pointers: list[CarryPointer] = []
    for index, line in enumerate(carry_surface_text.splitlines(), start=1):
        annotation = _ANNOTATION_RE.search(line)
        if annotation is not None:
            status = annotation.group("status").lower()
            target = annotation.group("target").lower()
            if not re.match(r"^\d+-\d+", target):
                raise ForwardPointerDriftError(
                    reason="annotation-target-malformed",
                    diagnostic=f"annotation at line {index} has a malformed target "
                    f"{annotation.group('target')!r}; expected a story-key like "
                    "'18-3' or '18-3-concurrent-env'",
                )
            if status in PENDING_STATUSES:
                pointers.append(
                    CarryPointer(
                        line_number=index,
                        target_key=target,
                        status=status,
                        source_kind="annotation",
                        line_text=line,
                    )
                )
            elif status not in KNOWN_FLIPPED_STATUSES:
                raise ForwardPointerDriftError(
                    reason="unknown-annotation-status",
                    diagnostic=f"annotation at line {index} has unrecognized "
                    f"status={annotation.group('status')!r}; expected one of "
                    f"{sorted(PENDING_STATUSES)} (pending) or "
                    f"{sorted(KNOWN_FLIPPED_STATUSES)} (flipped/retired)",
                )
        for inline in _INLINE_BINDING_RE.finditer(line):
            pointers.append(
                CarryPointer(
                    line_number=index,
                    target_key=inline.group("target"),
                    status="carries",
                    source_kind="inline",
                    line_text=line,
                )
            )
    return pointers


def resolve_done_target(target_key: str, done_story_keys: frozenset[str]) -> str | None:
    """Resolve a pointer ``target_key`` against the live ``done`` set.

    Returns the matched full ``done`` story-key, or ``None`` if the target is
    not (a prefix of) any ``done`` story. A target matches when it equals a
    done key exactly OR is a hyphen-bounded prefix of one (so the short
    ``18-3`` form binds ``18-3-concurrent-env-…``). The hyphen boundary keeps
    ``1-1`` from matching ``1-10a-…`` (``"1-10a-…".startswith("1-1-")`` is
    False).
    """
    for done_key in done_story_keys:
        if target_key == done_key or done_key.startswith(f"{target_key}-"):
            return done_key
    return None
