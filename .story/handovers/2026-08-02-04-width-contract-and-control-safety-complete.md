# ISS-002, T-003, and T-004 complete — width-control contract and safety bound

## Completed

- Resolved ISS-002 by making non-mapping `columns` metadata fall back to default automatic widths.
- Ratified T-003's normative automatic table-width contract in `docs/table-widths.md`, including activation aliases, classification/grouping, precedence, fitting, page controls, diagnostics, alignment independence, and semantic/accessibility preservation.
- Completed T-004 with a pure dependency-neutral `pdf/width_metadata.py` normalizer shared by parsed YAML and direct rendering entrypoints.
- Enforced safe defaults and payload-free warnings for malformed `table_widths`, `orientation`, `page_width_em`, and `columns` controls.
- Bound explicit automatic-width overrides to positive finite numeric/em values and rejected booleans, non-finite/huge values, unsupported units, expressions, malformed structures, and injection-like strings.
- Rescoped T-005 to exact fitting/accounting verification using the ratified em-only grammar.

## Validation

- Python 3.13 full suite: 172 passed.
- `git diff --check`: passed.
- Story validation: valid with zero findings.
- T-003 and T-004 final CODE_REVIEW lens rounds: full approval, zero findings.

## Commits

- `aca63fb` Handle invalid columns metadata safely
- `a4a44d4` Ratify automatic table-width contract
- `343cc4c` Normalize table-width front matter safely

## Current state

- Branch: `feature/table-widths`
- Worktree was clean after `343cc4c`.
- No push performed.
- Story's next recommendation is T-005, followed by ISS-003. T-005 should remove the now-unreachable ten-em fallback, prove exact accepted-width accounting across mixed columns and page budgets, and resolve ISS-003.
