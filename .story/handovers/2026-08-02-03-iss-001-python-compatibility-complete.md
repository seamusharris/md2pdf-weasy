# ISS-001 and T-012 completed — Python 3.14 native teardown compatibility bound

Resumed ISS-001 from the previous handover without discarding any uncommitted work. The existing .gitignore Storybloq runtime entries and all .story initialization/ledger files were preserved. No commit or push was made.

## Review decision

The first PLAN_REVIEW lens round rejected the tentative process-wide WeasyPrint FontConfiguration/render-lock workaround. A universal configuration is mutable through @font-face and could contaminate unrelated styles; a stylesheet-keyed process-lifetime cache would avoid that but creates unbounded native-memory growth. Test-quality also required deterministic acceptance criteria. The revised plan chose the evidence-based compatibility-bound path required by T-012. Round two approved with zero findings across all applicable core lenses.

The tentative changes in pdf/render.py and tests/test_render.py were removed completely, restoring both files to HEAD. The final product diff only:
- changes pyproject.toml requires-python from >=3.11 to >=3.11,<3.14;
- documents Python 3.11–3.13 support and the Python 3.14 native teardown exclusion in README.md and docs/getting-started.md;
- preserves the prior .gitignore Storybloq runtime entries.

## Compatibility matrix and validation

Failing evidence retained from the previous session:
- macOS arm64, Python 3.14.6, WeasyPrint 68.1, Pango 1.58.0;
- 2 abnormal exits in 10 fresh full-suite processes;
- 2 abnormal exits in 20 fresh tests/test_themes.py processes;
- assertions otherwise completed.

Supported candidate validated this session:
- macOS arm64, Python 3.13.13, WeasyPrint 68.1, Pango 1.58.0;
- focused tests/test_render.py: 27 passed;
- initial unsplit suite: 118 passed;
- 10/10 fresh full-suite processes exited 0;
- 20/20 fresh tests/test_themes.py processes exited 0;
- final post-review unsplit suite: 118 passed;
- git diff --check passed.

The standalone uv Python 3.13 interpreter required DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib to locate the same Homebrew native libraries. A clean Python 3.13 editable install accepted the metadata. Standard pip on Python 3.14.6 rejected the project with: Package 'md2pdf-weasy' requires a different Python: 3.14.6 not in '<3.14,>=3.11'.

Final CODE_REVIEW lenses activated security, error-handling, clean-code, and concurrency. The deterministic result was APPROVE, full coverage, zero findings, and no fix round.

## Ledger and worktree

ISS-001 is resolved with the matrix evidence. T-012 is complete. Storybloq validation returned valid with zero errors and zero warnings. Lesson L-001 records why native lifetime caching was rejected.

Current uncommitted worktree:
- modified: .gitignore, README.md, docs/getting-started.md, pyproject.toml
- untracked: .story/
- pdf/render.py and tests/test_render.py are clean relative to HEAD
- branch remains feature/table-widths at 2702309, synchronized with origin

Next action is user review and explicit approval before any commit. Do not push without separate approval.