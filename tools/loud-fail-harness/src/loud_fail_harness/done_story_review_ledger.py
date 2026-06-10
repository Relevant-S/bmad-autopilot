"""Done-story review-ledger parsers — Story 24.3 (Epic 24 Action #3).

The substrate half of the done-story review-ledger structural check. This
module holds the two pure parsers; the rule evaluation + CLI live in the
sibling :mod:`done_story_review_ledger_gate` (the gate-shape mirror of
:mod:`no_destructive_resume_lint`).

## What this codifies

Story 18.3 closed ``done`` while its story-doc ``### Review Findings``
ledger still carried unchecked ``[ ] [Review][Patch]`` / ``[ ] [Review]
[Decision]`` items — a *traceability* gap (the fixes had landed; the
ledger did not record it). This parser plus the gate joins
``sprint-status.yaml`` status × story-doc ledger so "did every review
finding get checked off before this story went ``done``?" becomes a
build-time-detectable invariant rather than a human-eyeball obligation.

## Two review-ledger conventions — this targets the meta-development one

* Product-runtime (Story 3.2, user-project docs): ``## Review Findings``
  with ``[Review][Patch] <marker-class>: …`` entries, NO checkboxes —
  consumed by :mod:`cross_state_recovery`. NOT this module's target.
* Meta-development (this project's ``_bmad-output/implementation-
  artifacts/*.md``): ``### Review Findings`` with ``[ ]``/``[x]``
  checkboxes, produced by the ``bmad-code-review`` skill. THIS is the
  target. Because the parser keys off the ``- [ ] [Review][…]`` list-item
  shape (not the heading level) it tolerates both ``##`` and ``###``.
"""

from __future__ import annotations

import re
from typing import Final, NamedTuple

import yaml

__all__ = [
    "DoneStoryReviewLedgerError",
    "ReviewLedgerItem",
    "iter_done_story_keys",
    "iter_review_ledger_items",
]

#: Story-vs-epic-vs-retro discrimination — the same shape the create-story
#: workflow uses. Matches ``24-3-…`` and alpha-suffix keys ``1-10a-…`` but
#: not ``epic-24`` / ``epic-24-retrospective`` / metadata keys.
_STORY_KEY_RE: Final[re.Pattern[str]] = re.compile(r"^\d+-\d+[a-z]?-")

#: Fenced-code-block stripper, copied from
#: ``cross_state_recovery._FENCED_CODE_BLOCK_RE`` so ``[ ][Review][…]``
#: text inside an example block is not misread as a real ledger item.
_FENCED_CODE_BLOCK_RE: Final[re.Pattern[str]] = re.compile(
    r"```.*?```|~~~.*?~~~", re.DOTALL
)

#: Checkbox-aware sibling of ``cross_state_recovery._REVIEW_TAXONOMY_RE``:
#: also captures the ``[ ]``/``[x]`` state and is anchored to a ``- `` list
#: marker so inline-prose ``[Review]`` mentions (and the documenting
#: examples in the story doc) are NOT matched. The tag space is left
#: open-ended (``[^\]]+``) — the rules key off ``state`` and a ``Defer``
#: substring, never an exhaustive tag enum.
_REVIEW_ITEM_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*-\s*\[(?P<state>[ xX])\]\s*\[Review\]\[(?P<tag>[^\]]+)\]", re.MULTILINE
)


class DoneStoryReviewLedgerError(Exception):
    """Raised on substrate-level failures parsing sprint-status (Pattern 5).

    Loud-fail / named-invariant convention — analogous in shape to
    :class:`cross_state_recovery.CrossStateRecoveryError`. A malformed or
    structurally-wrong sprint-status is a harness-level error (the gate
    maps it to exit 2), never a silent empty done-set.

    Attributes:
        reason: Short kebab-case discriminator naming the failure.
        diagnostic: Human-readable diagnostic + remediation hint (NFR-O5).
    """

    def __init__(self, *, reason: str, diagnostic: str) -> None:
        self.reason = reason
        self.diagnostic = diagnostic
        super().__init__(f"DoneStoryReviewLedgerError[{reason}]: {diagnostic}")


class ReviewLedgerItem(NamedTuple):
    """A single ``- [ ]``/``- [x] [Review][<tag>]`` ledger item.

    A lightweight internal parse-result value object (NOT a Pydantic
    BaseModel ingress surface — its fields are display-only diagnostic text,
    not identifier/path ingress, so the input-hardening gate's
    model-classification does not govern it). Immutable by construction.
    """

    line_number: int
    state: str
    tag: str
    line_text: str


def iter_done_story_keys(sprint_status_text: str) -> list[str]:
    """Yield the story keys whose ``development_status`` value is ``"done"``.

    Filters to keys matching :data:`_STORY_KEY_RE` so ``epic-N`` /
    ``epic-N-retrospective`` / project-metadata keys are excluded. Order
    follows the mapping's declared order (insertion order under
    ``yaml.safe_load``). Raises :class:`DoneStoryReviewLedgerError` on a
    malformed / structurally-wrong sprint-status — never a silent empty
    set (loud-fail).
    """
    try:
        raw = yaml.safe_load(sprint_status_text)
    except yaml.YAMLError as exc:
        raise DoneStoryReviewLedgerError(
            reason="sprint-status-not-valid-yaml",
            diagnostic=f"sprint-status is not valid YAML: {exc}",
        ) from exc
    if not isinstance(raw, dict):
        raise DoneStoryReviewLedgerError(
            reason="sprint-status-not-a-mapping",
            diagnostic="sprint-status did not parse to a mapping; expected a "
            "top-level mapping with a `development_status:` key",
        )
    development_status = raw.get("development_status")
    if not isinstance(development_status, dict):
        raise DoneStoryReviewLedgerError(
            reason="development-status-missing",
            diagnostic="sprint-status has no `development_status:` mapping; "
            "cannot enumerate `done` stories",
        )
    return [
        key
        for key, value in development_status.items()
        if isinstance(key, str) and value == "done" and _STORY_KEY_RE.match(key)
    ]


def iter_review_ledger_items(doc_text: str) -> list[ReviewLedgerItem]:
    """Extract every ``- [ ]``/``- [x] [Review][<tag>]`` ledger item.

    Fenced code blocks are blanked (newline-for-newline so line numbers are
    preserved) before matching, so ``[Review]`` mentions inside example
    blocks are not counted. Matching is per-line (the named regex's leading
    ``^\\s*`` would otherwise let ``\\s`` cross a newline under
    ``re.MULTILINE`` and anchor the match on a preceding blank line). The
    list-item anchor excludes inline-prose / narrative ``[Review]`` mentions.
    """
    blanked = _FENCED_CODE_BLOCK_RE.sub(
        lambda m: "\n" * m.group(0).count("\n"), doc_text
    )
    original_lines = doc_text.splitlines()
    items: list[ReviewLedgerItem] = []
    for index, line in enumerate(blanked.splitlines(), start=1):
        match = _REVIEW_ITEM_RE.match(line)
        if match is None:
            continue
        items.append(
            ReviewLedgerItem(
                line_number=index,
                state=match.group("state"),
                tag=match.group("tag"),
                line_text=original_lines[index - 1],
            )
        )
    return items
