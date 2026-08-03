# Authorized downstream canary

## Current status

No authorized private consumer is recorded. The reference-only
[`downstream-consumers.json`](downstream-consumers.json) registry is intentionally
empty, and the T-013 `consumer_canary` entitlement remains `not_verified`.
Consequently, the harness exits before acquiring a lease, inspecting an
installation, importing `pdf`, allocating temporary space, or rendering.

T-014 creates coverage infrastructure only. T-017 owns execution against an
exact candidate after a separately approved consumer, environment, and recipient
have been added to both entitlement and consumer records. Neither ticket permits
consumer documents, font files, credentials, licences, package artifacts, or
result attachments to be copied into this repository.

## Coverage contract

An authorized run covers:

| Check | Evidence produced inside the ephemeral run |
|---|---|
| Python API | Calls `parse_front_matter`, `md_to_html`, `postprocess`, `build_html`, and `build_pdf` through the ratified installed package. |
| Relative resources | Uses the invented SVG and relative link in `tests/canary/downstream.md`. |
| `base_url` | Supplies the ephemeral fixture directory to every PDF render. |
| Front matter | Checks the invented title, language, and selected theme. |
| Themes | Exercises alpine, wnc, regrading, neutral, and compact. |
| Private Git installation | Reads the already-installed distribution's PEP 610 `direct_url.json`; requires non-editable Git provenance and package bytes matching the exact candidate tree. |
| Opt-out | Verifies `table_widths: false` produces no automatic colgroup. |
| Rollback | Verifies the full rollback ID exists locally as an exact commit object; it never checks out or installs it. |

The fixture is invented and repository-owned. Do not replace it with a private
consumer file. A consumer may add its own checks only inside its authorized
environment and should report the bounded result fields, not input or output
documents.

## Authorization and registry

An entry may be added only after separate explicit approval. The stable registry
stores bounded opaque identifiers, the exact `consumer_canary` entitlement tuple,
a provenance reference, and feature-set ID. It never stores names, URLs, run
commits, content, or results. Candidate/rollback commits and the opt-out control
are per-run CLI inputs.

The harness validates the T-013 entitlement before reading the registry. Both
records must match the same exact environment and recipient. Generic labels do
not authorize a real consumer.

## Consumer-owned execution model

The consumer supplies an already-present, dedicated checkout and virtual
environment that no other job modifies. The harness does not clone, fetch,
install, build, package, check out, upload, or attach anything. It requires:

- canonical full candidate and rollback commit IDs;
- a clean checkout at the candidate commit;
- the immutable checkout tree returned by entitlement preflight;
- a non-editable PEP 610 Git install at that exact commit;
- a safe absolute lease path and temporary parent owned by the consumer; and
- cooperation from all environment modifiers with the same lease.

The command shape, shown for documentation only, is:

```bash
python -m tools.downstream_canary \
  --consumer approved_consumer_id \
  --environment approved_environment_id \
  --recipient approved_recipient_id \
  --candidate <full-candidate-commit> \
  --rollback f565357a9e6ba975ae9e1699f27be876825b149e \
  --opt-out table_widths_false \
  --lease-path /consumer-owned/state/md2pdf-canary.lock \
  --temp-parent /consumer-owned/tmp
```

It fails today because no exact authorization/consumer exists. Do not work
around that decision, and do not use this command as an installation recipe.

## Isolation, cleanup, and result

After authorization, the harness holds a non-blocking POSIX lease across initial
provenance, API scenarios, cleanup, final provenance, and result publication.
It reads the registry and sanitized fixtures from the immutable entitled Git
tree, not mutable checkout paths. It snapshots the checkout, installed files,
candidate package manifest, input digest, and hashed PEP 610 metadata before and
after the scenarios. Any mutation or lease contention fails closed.

Before importing `pdf`, the harness copies the exact installed package inventory
into the ephemeral directory and verifies the copied bytes against the candidate
Git-tree manifest. A restricted import path then loads `pdf` only from that
verified copy. The mutable installation is therefore provenance evidence, never
the executable import source. Candidate imports and all render calls run in a
fresh isolated interpreter, so the coordinator never rewrites its own import
state or redirects its own standard output.

All fixture and render outputs live under one newly created directory beneath
the consumer's temporary parent. Success JSON is constructed in memory and
printed only after that tree is removed and final identity checks pass. Cleanup
failure never reports success; a bounded path-free warning says residue may
remain. A simultaneous scenario and cleanup failure preserves the scenario's
failure category and adds the warning.

The only successful fields are schema/status, opaque consumer/environment IDs,
candidate commit/tree, the sanitized aggregate input digest, rollback commit,
opt-out identifier, and the fixed check IDs. The result contains no recipient,
repository URL, filesystem path, package metadata, document content, or
artifact.

## Rollback interpretation

The canary records both narrow and full controls:

- `table_widths_false` disables only automatic widths while retaining current
  language and PDF/UA behavior.
- The exact v0.1.0 commit is an emergency full rollback whose accessibility
  differences remain documented in [the migration guide](v0.1.0-migration.md).

T-014 only verifies that rollback commit as a local object. An authorized T-017
run may test the consumer's rollback in place; it must not transfer an artifact
or import its private output here.
