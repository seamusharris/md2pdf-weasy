# T-005 and ISS-003 complete — deterministic exact-width fitting validated

## Completed

- Completed T-005 by removing the unreachable ten-em non-em fallback and making explicit numeric/decimal-em widths use one normalized em value for fitting and CSS emission.
- Added a pure fitting result with explicit `fit`, `scaled`, and `unresolved_overflow` outcomes shared by colgroup emission and diagnostics.
- Preserved explicit author widths and numeric ladder rungs while scaling only automatic wide columns; fixed-only overflow is no longer mislabeled as fitting.
- Made overflow diagnostics accurate for default portrait, landscape, and custom fitting budgets, with landscape advice only when actionable.
- Made em-string normalization precision-preserving at float accounting precision and idempotent without exponent notation, including very large finite decimal strings.
- Added overflow-safe aggregate accounting so multiple individually finite widths cannot abort rendering when their total exceeds the float range.
- Resolved ISS-003 with the exact accepted-width contract and validation evidence.
- Preserved the valid out-of-scope clean-code finding as ISS-005 and linked it to T-005 in the contract phase.

## Review decisions

- PLAN_REVIEW approved after one minor clean-code refinement: fitting calculation now returns a named outcome consumed by emission and diagnostics.
- CODE_REVIEW required four rounds (minimum three). Review-found precision, serialization, aggregate-overflow, diagnostic, and branch-coverage gaps were fixed.
- Final lens verdict: APPROVE, full coverage, zero findings, no further fix round.
- Extracting the full automatic-width subsystem from the large `table_transforms.py` module was deferred as ISS-005 rather than broadening T-005.

## Validation

- Focused exact-width/normalization suite: 103 passed after the final precision fix.
- Full suite on Python 3.14.6: 185 passed.
- Supported Python 3.13.13 full suite: 185 passed.
- `git diff --check`: passed.
- Story validation: valid, zero errors, zero warnings.
- Worktree clean after commits.

## Commits

- `ee1d390` — feat: verify deterministic explicit-width fitting (T-005)
- `e50f657` — fix: resolve explicit-width accounting issue (ISS-003)
- `adef90b` — chore: link width refactor follow-up to T-005

## Current state and next work

- Branch: `feature/table-widths`
- Branch is seven commits ahead of `origin/feature/table-widths`.
- No push performed.
- T-005 is complete; ISS-003 is resolved.
- ISS-005 remains open as the review-filed automatic-width module extraction follow-up.
- Continue with Story's next unblocked recommendation after reloading context; do not expand into ISS-005 unless it ranks appropriately against the contract/rendering backlog.