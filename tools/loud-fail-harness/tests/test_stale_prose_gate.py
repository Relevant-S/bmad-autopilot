"""Contract-coverage corpus for the stale-prose gate (Story 22.6 G1).

Drives the gate over the live tree (baseline pass — the witnessed 19→20→21
recurrence is already cleaned) and over synthetic prose proving it catches the
precise failure it exists to catch (a present-tense canonical claim contradicting
the live marker-taxonomy schema_version / closed-set count) WITHOUT firing on
historical lineage or on the other schemas' versions.

AC-1 — canonical-derivation + anchored present-tense scan:
    [x] test_canonical_values_real_taxonomy
    [x] test_baseline_real_tree_is_clean       (the live tree passes)
    [x] test_stale_version_claim_fires         (negative witness — version)
    [x] test_stale_count_claim_fires           (negative witness — count)
    [x] test_canonical_value_claim_does_not_fire
    [x] test_lineage_arrow_does_not_fire
    [x] test_lineage_v1_class_does_not_fire
    [x] test_other_schema_version_without_taxonomy_anchor_does_not_fire
    [x] test_docstring_prose_is_scanned
    [x] test_findings_are_byte_stable_ordered

AC-1 — suppression pragma (the LINT.IfChange / NO_IFTTT escape hatch):
    [x] test_pragma_same_line_suppresses
    [x] test_pragma_line_above_suppresses

AC-1 CLI + harness-level error:
    [x] test_main_exits_zero_on_clean
    [x] test_main_exits_one_on_stale_fixture
    [x] test_main_exit_two_when_taxonomy_missing
    [x] test_main_exit_two_on_malformed_taxonomy

AC-4 — boundary witness (build-time gate, NO runtime marker).
"""

from __future__ import annotations

import pathlib

from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.stale_prose_gate import (
    _SRC_REL,
    _TAXONOMY_REL,
    canonical_values,
    evaluate_prose,
    main,
    run_stale_prose_gate,
)

_REPO_ROOT = find_repo_root()
_TAXONOMY = _REPO_ROOT / _TAXONOMY_REL
_SRC_DIR = _REPO_ROOT / _SRC_REL


def _evaluate(text: str, *, version: str = "1.20", count: int = 44) -> list:
    return evaluate_prose(
        source_path=pathlib.Path("synthetic.py"),
        prose_line_numbers=None,
        text=text,
        canonical_version=version,
        canonical_count=count,
    )


def test_canonical_values_real_taxonomy() -> None:
    version, count = canonical_values(_TAXONOMY)
    assert version == "1.21"
    assert count == 44


def test_baseline_real_tree_is_clean() -> None:
    result = run_stale_prose_gate(
        taxonomy_path=_TAXONOMY,
        src_dir=_SRC_DIR,
        doc_paths=[_REPO_ROOT / "docs" / "implementation-patterns.md"],
    )
    assert result.findings == (), [f.diagnostic for f in result.findings]
    assert result.canonical_schema_version == "1.21"
    assert result.canonical_closed_set_count == 44


def test_stale_version_claim_fires() -> None:
    findings = _evaluate("# the marker-taxonomy schema_version is 1.12 today")
    assert [f.rule for f in findings] == ["stale-version-claim"]
    assert findings[0].found == "1.12"


def test_stale_count_claim_fires() -> None:
    findings = _evaluate("# the top-level 34-class closed-set is the invariant")
    assert [f.rule for f in findings] == ["stale-count-claim"]
    assert findings[0].found == "34"


def test_canonical_value_claim_does_not_fire() -> None:
    assert _evaluate("# marker-taxonomy schema_version is 1.20 (current)") == []
    assert _evaluate("# the 44-class closed-set is the live invariant") == []


def test_lineage_arrow_does_not_fire() -> None:
    # Changelog arrow — a historical transition, not a present claim.
    assert _evaluate("# marker-taxonomy schema_version 1.19 -> 1.20 (Story X)") == []
    assert _evaluate("# closed-set 43 -> 44; the 43-class set grew") == []


def test_lineage_v1_class_does_not_fire() -> None:
    assert _evaluate("# reused per the marker-taxonomy v1 27-class closed-set") == []
    assert _evaluate("# schemas/marker-taxonomy.yaml (schema_version 1.6). Consumed AS-IS.") == []


def test_other_schema_version_without_taxonomy_anchor_does_not_fire() -> None:
    # run-state / epic-run-state schema_versions are NOT the marker taxonomy's;
    # the taxonomy anchor is what disambiguates.
    assert _evaluate("# RunState schema_version is 1.3 at landing") == []
    assert _evaluate('    schema_version: Literal["1.0"]  # epic-run-state') == []


def test_docstring_prose_is_scanned() -> None:
    source = '"""Doc: the marker-taxonomy schema_version is 1.05 here."""\n'
    findings = evaluate_prose(
        source_path=pathlib.Path("m.py"),
        prose_line_numbers={1},
        text=source,
        canonical_version="1.20",
        canonical_count=44,
    )
    assert [f.rule for f in findings] == ["stale-version-claim"]


def test_pragma_same_line_suppresses() -> None:
    text = "# marker-taxonomy schema_version is 1.12  # stale-prose-ok: changelog"
    assert _evaluate(text) == []


def test_pragma_line_above_suppresses() -> None:
    text = (
        "# stale-prose-ok: historical reference below\n"
        "# the marker-taxonomy schema_version is 1.12\n"
    )
    assert _evaluate(text) == []


def test_findings_are_byte_stable_ordered() -> None:
    text = (
        "# the 30-class closed-set\n"
        "# marker-taxonomy schema_version is 1.12\n"
        "# the 31-class closed-set\n"
    )
    findings = _evaluate(text)
    keys = [(str(f.source_path), f.line_number, f.rule) for f in findings]
    assert keys == sorted(keys)
    assert len(findings) == 3


def test_main_exits_zero_on_clean() -> None:
    assert main([]) == 0


def test_main_exits_one_on_stale_fixture(tmp_path: pathlib.Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "stale.py").write_text(
        '"""The marker-taxonomy schema_version is 1.07 (stale)."""\n',
        encoding="utf-8",
    )
    exit_code = main(["--src-dir", str(src), "--doc", str(tmp_path / "none.md")])
    assert exit_code == 1


def test_main_exit_two_when_taxonomy_missing(tmp_path: pathlib.Path) -> None:
    assert main(["--taxonomy", str(tmp_path / "nope.yaml")]) == 2


def test_main_exit_two_on_malformed_taxonomy(tmp_path: pathlib.Path) -> None:
    bad = tmp_path / "taxonomy.yaml"
    bad.write_text("just a string, not a mapping\n", encoding="utf-8")
    assert main(["--taxonomy", str(bad)]) == 2


# --------------------------------------------------------------------------- #
# Story 22.6 D1 tightened lineage: broad substrings removed / word-bounded    #
# --------------------------------------------------------------------------- #


def test_tightened_lineage_no_longer_suppresses_common_words() -> None:
    # Words removed from _LINEAGE (mirror, enumerat, introduc, once ) now
    # allow a genuine stale claim on those lines to fire.
    assert _evaluate("# marker-taxonomy schema_version is 1.12, mirroring the bundle header") != []
    assert _evaluate("# enumerating marker-taxonomy schema_version 1.12 classes for the spec") != []
    assert _evaluate("# introduction to marker-taxonomy schema_version 1.12") != []
    assert _evaluate("# marker-taxonomy schema_version is 1.12 once the release is cut") != []
    # 'consumers' (plural) no longer suppresses; 'consumed' (past-tense) still does.
    assert _evaluate("# consumers of the marker-taxonomy schema_version 1.12 API") != []
    assert _evaluate("# marker-taxonomy schema_version 1.12. Consumed AS-IS.") == []


def test_tightened_lineage_past_tense_still_suppresses() -> None:
    # Past-tense / explicit lineage words still suppress correctly.
    assert _evaluate("# marker-taxonomy schema_version was 1.12 at the time") == []
    assert _evaluate("# marker-taxonomy schema_version 1.12 landed in Story 10.3") == []
    assert _evaluate("# marker-taxonomy schema_version bumped from 1.12 to current") == []
