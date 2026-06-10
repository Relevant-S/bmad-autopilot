"""Parser-coverage matrix for the done-story review-ledger library (Story 24.3).

Unit-tests the two pure parsers directly. The gate-level (rules + CLI) tests
live in :mod:`tests.test_done_story_review_ledger_gate`.

AC-1 — sprint-status `done`-story enumeration:
    [x] test_iter_done_story_keys_returns_only_done_story_shaped_keys
    [x] test_iter_done_story_keys_excludes_epic_and_retrospective_and_metadata
    [x] test_iter_done_story_keys_preserves_declaration_order
    [x] test_iter_done_story_keys_raises_on_malformed_yaml
    [x] test_iter_done_story_keys_raises_on_missing_development_status

AC-2 — ledger parse (fence-stripped, list-item-scoped):
    [x] test_iter_review_ledger_items_captures_state_tag_line_number
    [x] test_iter_review_ledger_items_ignores_fenced_code_block_mentions
    [x] test_iter_review_ledger_items_ignores_inline_prose_mentions
    [x] test_iter_review_ledger_items_line_numbers_survive_fence_stripping
    [x] test_iter_review_ledger_items_open_ended_tag_space
"""

from __future__ import annotations

import pytest

from loud_fail_harness.done_story_review_ledger import (
    DoneStoryReviewLedgerError,
    iter_done_story_keys,
    iter_review_ledger_items,
)

_SPRINT_STATUS = """\
generated: 2026-04-25
project: bmad_automation
development_status:
  epic-1: done
  1-1-harness-substrate-skeleton: done
  1-2-some-other-story: review
  epic-1-retrospective: done
  24-3-done-story-review-ledger-structural-check: in-progress
  18-3-concurrent-env-provisioning-discipline-fr7-extension: done
"""


def test_iter_done_story_keys_returns_only_done_story_shaped_keys() -> None:
    keys = iter_done_story_keys(_SPRINT_STATUS)
    assert keys == [
        "1-1-harness-substrate-skeleton",
        "18-3-concurrent-env-provisioning-discipline-fr7-extension",
    ]


def test_iter_done_story_keys_excludes_epic_and_retrospective_and_metadata() -> None:
    keys = iter_done_story_keys(_SPRINT_STATUS)
    assert "epic-1" not in keys
    assert "epic-1-retrospective" not in keys
    assert all(not k.startswith("epic-") for k in keys)


def test_iter_done_story_keys_includes_alpha_suffix_keys() -> None:
    text = """\
development_status:
  1-10a-pluggability-no-cross-references-ci-gate-fr62: done
  1-10b-story-doc-section-allowlist-contract-fr66-nfr-s5: done
  1-12a-documentation-promotion-boundary-docs: done
  epic-1: done
"""
    keys = iter_done_story_keys(text)
    assert "1-10a-pluggability-no-cross-references-ci-gate-fr62" in keys
    assert "1-10b-story-doc-section-allowlist-contract-fr66-nfr-s5" in keys
    assert "1-12a-documentation-promotion-boundary-docs" in keys
    assert "epic-1" not in keys


def test_iter_done_story_keys_preserves_declaration_order() -> None:
    text = """\
development_status:
  9-5-second: done
  1-1-first: done
"""
    assert iter_done_story_keys(text) == ["9-5-second", "1-1-first"]


def test_iter_done_story_keys_raises_on_malformed_yaml() -> None:
    with pytest.raises(DoneStoryReviewLedgerError) as exc_info:
        iter_done_story_keys("development_status:\n  - [unbalanced\n")
    assert exc_info.value.reason == "sprint-status-not-valid-yaml"


def test_iter_done_story_keys_raises_on_missing_development_status() -> None:
    with pytest.raises(DoneStoryReviewLedgerError) as exc_info:
        iter_done_story_keys("project: bmad_automation\n")
    assert exc_info.value.reason == "development-status-missing"


_DOC_WITH_LEDGER = """\
# Story 9.9

### Review Findings

- [x] [Review][Patch] something resolved
- [ ] [Review][Decision] still open
- [x] [Review][Defer] deferred to deferred-work.md:9
"""


def test_iter_review_ledger_items_captures_state_tag_line_number() -> None:
    items = iter_review_ledger_items(_DOC_WITH_LEDGER)
    assert [(i.state, i.tag) for i in items] == [
        ("x", "Patch"),
        (" ", "Decision"),
        ("x", "Defer"),
    ]
    assert items[0].line_number == 5
    assert items[1].line_number == 6


def test_iter_review_ledger_items_ignores_fenced_code_block_mentions() -> None:
    doc = """\
### Review Findings

```
- [ ] [Review][Patch] this is an EXAMPLE inside a fence
```

- [x] [Review][Patch] real item
"""
    items = iter_review_ledger_items(doc)
    assert len(items) == 1
    assert items[0].state == "x"


def test_iter_review_ledger_items_ignores_inline_prose_mentions() -> None:
    doc = (
        "### Review Findings\n\n"
        "A finding of the shape `[ ][Review][Patch]` is normal in flight.\n"
        "The narrative mentions [Review][Decision] without a list marker.\n"
    )
    assert iter_review_ledger_items(doc) == []


def test_iter_review_ledger_items_line_numbers_survive_fence_stripping() -> None:
    doc = """\
### Review Findings

```
fenced line 1
fenced line 2
```

- [ ] [Review][Patch] real item after a fence
"""
    items = iter_review_ledger_items(doc)
    assert len(items) == 1
    assert items[0].line_number == 8


def test_iter_review_ledger_items_open_ended_tag_space() -> None:
    doc = (
        "- [x] [Review][Decision→Patch] arrowed tag\n"
        "- [x] [Review][Dismissed] dismissed tag\n"
    )
    items = iter_review_ledger_items(doc)
    assert [i.tag for i in items] == ["Decision→Patch", "Dismissed"]
