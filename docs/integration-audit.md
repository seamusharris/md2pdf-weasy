# Immutable integration candidate audit

This record audits candidate `0b22ebd9efb19ec25247a85fd39796aa2907b6d6` without modifying it. The candidate tree is `dd8a0a74f066df7dbce772fdc3061dc845f4d1a9`; the fixed local base is `0393826337b59f8a10be9f201083541fa7f4a49f`, and the original fifteen-commit stack ends at `27023098530836c7c4c2c822fb67a5fd149f9ec9`.

The canonical machine-readable record is [integration-audit.json](integration-audit.json). It records 15 original commits, 18 stabilization commits, 148 changed paths, history digest `7fc558af748c6f4881295f7d10d6af1d585c7b9df27273064524bf69471f84b4`, diff digest `3afa0b83b7d72a351aa3e7593c9501b469ed6871b9a5149ca1b11b4008fccece`, and changed-path digest `91d636a7690a6ec7196b3ea2fedcb9657fb159368e6a44370eaf8520bee921d3`.

## Validation outcome

- Exact ancestry, ordered history, merge base, candidate object, and tree: pass.
- Immutable `git diff --check`, changed-path inventory, and candidate-blob conflict-marker checks: pass.
- Python 3.13 full suite (`{python-3.13} -m pytest -q -p no:cacheprovider`) in the deny-by-default candidate sandbox: not run.
- Current-interpreter full suite (`{current-python} -m pytest -q -p no:cacheprovider`) in the deny-by-default candidate sandbox: not run.
- Focused visual-acceptance and v0.1.0 compatibility checks (`{python-3.13} -m pytest -q -p no:cacheprovider tests/test_visual_acceptance.py tests/test_compatibility.py`) in that sandbox: not run.
- Sandbox startup probe using `sandbox-exec`, a deny-by-default profile, and `/usr/bin/true`: fail-closed because the host aborted the sandbox process.
- Two complete audit invocations: byte-identical 2,181-byte canonical records, both exiting nonzero.

## Decision

**NO-GO.** Local integration, downstream verification, packaging, tagging, and publication remain blocked. A later run may replace this record with a go decision only after the same immutable candidate completes every isolated validation command. No candidate source, font bytes, rendered output, consumer data, credentials, local filesystem paths, or temporary paths are retained here.
