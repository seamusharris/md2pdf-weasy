# Local packaging gates

## Current decision

**Blocked; no package artifact was created.** The canonical machine record is
[`local-packaging-gates.json`](local-packaging-gates.json). It records the
checked source identity, both upstream prerequisite outcomes, and every
downstream gate as not run. This page is static policy guidance; it does not
duplicate mutable result fields from the JSON record.

This blocked record is a safe prerequisite check, not completion of T-016's
authorized build, archive inspection, clean-install, CLI, and render gates.
T-016 remains incomplete until those gates can run in an authorized environment.

The two independent blockers are:

- immutable integration evidence has no accepted activation ref; and
- the exact `package_artifact` / `owner_workstation` / `owner` entitlement is
  `not_verified`.

Either denial is sufficient to prohibit wheel/sdist creation. The full suite,
visual review, archive inspection, clean installation, CLI checks, and smoke
renders cannot be credited from the editable development environment and remain
not run for this gate.

## Reproduce the artifact-free check

Run from the repository root:

```bash
make local-packaging-gates
```

The expected blocked outcome writes one bounded canonical JSON line to stdout.
The underlying Python module exits `1`; because Make treats that intentional
blocked status as a failed recipe, `make local-packaging-gates` normally exits
`2`. Diagnostics or unexpected failures use stderr and never grant a GO result.
The command acquires the shared integration lease, evaluates both read-only
prerequisites, rechecks source identity, and never writes to the checkout or
creates a package artifact.

## Authorized rerun requirements

Do not run packaging commands unless T-015 has an accepted immutable result and
T-013 authorizes the exact source tree for the exact local tuple. A later
authorized runner must also satisfy the reviewed T-016 plan: offline
hash-verified dependencies, a credential-free network-denied sandbox, private
ephemeral storage, bounded streaming archive inspection, supervised subprocess
cleanup, installed-wheel PDF/HTML accessibility checks, and operator-owned
evidence publication. Expanded tool permissions do not replace either
prerequisite.
