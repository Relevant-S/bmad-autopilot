# Hook script effective-line counting rule (FR61 + NFR-S4)

Canonical reference for the FR61 ≤20-lines-of-bash effective-line counting rule
enforced by `hook_budget_gate.py`. The gate's `count_effective_lines` function is
the machine-readable implementation; this document is the human-readable
canonical form. AC-9's `test_counting_rule_doc_in_sync` test parses the worked
examples below and asserts each round-trips through `count_effective_lines` with
the declared expected count — if the doc and implementation drift, the test
fires loudly.

## Rule

For each `.sh` file under the inner repo's `hooks/` directory at the top level,
the gate computes the number of **effective** lines per the following four
clauses, applied line-by-line and stateless except for the line-1 shebang
special case:

1. **Shebang on line 1 only is always skipped.** Defined as: line 1 of the file
   begins with the literal two-character sequence `#!`. This skip is
   line-1-only — a `#!`-prefixed line appearing at any other position is treated
   as a comment-only line under clause 3, not as a shebang. If line 1 does not
   start with `#!`, no shebang skip occurs and line 1 is counted under the
   normal clauses.
2. **Blank lines are always skipped.** A blank line is one whose `.strip()`
   evaluates to an empty string (i.e. the line was empty or contained only
   whitespace — spaces, tabs, `\n`, `\r`, `\f`, `\v`).
3. **Comment-only lines are always skipped.** A comment-only line is one whose
   `.strip()` begins with the character `#`. Leading whitespace before the `#`
   does not change this — an indented comment is still comment-only.
4. **Everything else counts.** This includes lines containing
   `code # inline comment` (where the `#` appears mid-line, not at the start of
   the stripped content), continuation backslashes (`some_command \`), heredoc
   bodies (every line between `<<EOF` and `EOF` counts because heredocs are
   runtime-effective code), function definitions, and bash control-flow
   keywords (`if`, `then`, `else`, `fi`, `for`, `do`, `done`, `case`, `esac`,
   closing braces `}`, etc.).

The rule does **not** strip syntactic noise (e.g. `}`, `fi`, `done` lines count;
they are bash control flow, not aesthetic). The rule does **not** apply lookahead
heuristics (e.g. a comment-only line is not "absorbed" into the next code line).

The cap is **20 effective lines per hook script** (FR61). When the gate computes
a per-file effective-line count greater than 20, it emits one
`line_violation` finding for that file and exits 1.

## Worked examples

Each example below is a small bash snippet plus the expected effective-line
count. The `test_counting_rule_doc_in_sync` test parses these pairs and asserts
that `count_effective_lines(<temp file with snippet>) == <expected count>`. Add
new examples here as the rule is exercised against new edge cases.

### Example 1 — shebang on line 1 skipped

```bash
#!/bin/bash
echo foo
```

Expected count: 1

### Example 2 — blank line skipped

```bash
echo foo

echo bar
```

Expected count: 2

### Example 3 — comment-only line skipped

```bash
# this is a comment
echo foo
```

Expected count: 1

### Example 4 — indented comment-only line skipped

```bash
    # nested comment
echo foo
```

Expected count: 1

### Example 5 — `code # inline comment` counted as code

```bash
echo foo # this is an inline comment
```

Expected count: 1

### Example 6 — heredoc body counted

```bash
cat <<EOF
line one
line two
line three
EOF
```

Expected count: 5

### Example 7 — control-flow keywords counted

```bash
if true; then
    echo a
fi
```

Expected count: 3

### Example 8 — mid-file shebang treated as comment

```bash
echo foo
#!/bin/sh
echo bar
```

Expected count: 2

## Why this rule resists gaming

Three properties of the rule make it hard to game:

1. **Spreading code across many short lines does not help.** The line count is
   the count of code-bearing lines. Many short lines push the count up, not
   down — every additional code-bearing line adds to the total. There is no
   per-line character budget the rule could be played against.

2. **Hiding code behind comments tightens the budget against the practitioner,
   not loosens it.** Comments are skipped, so adding comments to a hook script
   does not reduce its effective count from a *fixed-target* standpoint. From a
   practitioner's local-edit standpoint, adding comments around existing code
   leaves the count unchanged while making the script longer in raw lines —
   the comments are free, but the code budget is still 20.

3. **Moving code into heredocs or function bodies does not hide it.** Heredoc
   bodies count line-by-line. Function-body lines count line-by-line. The rule
   sees the whole file as a flat sequence of lines and applies the four
   clauses statelessly — there is no syntactic subset (function bodies, heredoc
   bodies, subshells) the rule looks past.

Combined, these properties mean the rule cannot be circumvented without
*actually* shrinking the script's code-bearing lines — i.e. by making the hook
do less work, OR by factoring logic into a non-hook artifact (a helper called
by the hook). Both outcomes are aligned with the FR60 + FR61 + NFR-S4
intent: hooks are mechanical-side-effect glue, not application logic.

## Cross-references

- **PRD § FR60** (line 895) — `_bmad-output/planning-artifacts/prd.md`. The
  ≤3 hooks budget invariant; CI-enforced.
- **PRD § FR61** (line 896) — `_bmad-output/planning-artifacts/prd.md`. The
  ≤20-lines-of-bash per-hook invariant; CI-enforced.
- **PRD § NFR-S4** (line 972) — `_bmad-output/planning-artifacts/prd.md`. Hook
  script trust model; "the 20-lines-of-bash heuristic + CI enforcement bounds
  the hook attack surface."
- **architecture.md § "CI-enforced patterns"** (line 1031) —
  `_bmad-output/planning-artifacts/architecture.md`. Names this gate as the
  implementation of the two CI-enforced patterns "≤3 hooks budget (per FR60)"
  and "20-lines-of-bash hook size limit (per FR61)".
- **`hook_budget_gate.py`** —
  `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/hook_budget_gate.py`.
  The machine-readable counting-rule implementation. The
  `count_effective_lines` function is the canonical algorithm; this document
  and that function MUST stay byte-for-byte equivalent in their behavior.
