# Proprietary distribution entitlement

## Current decision

**Not verified — do not distribute.** As reviewed on 3 August 2026, the
repository contains 94 Adobe OTF files (64 Minion Pro and 30 Myriad Pro) but no
reference to the governing EULA, acquisition channel, build-environment
entitlement, matching recipient licence, or distribution approval. The local
description “personal-use licensed” is not evidence of transfer rights.

Until separately approved evidence is recorded for an exact operation,
environment, and recipient, do not:

- create a wheel, source archive, package attachment, or other package artifact;
- run a consumer canary that transfers this source tree or its Adobe fonts;
- copy the repository to CI, a shared runner, a server, or another workstation;
- upload to a public or private registry, release, ticket, chat, or file store; or
- attach a licence document, font file, Adobe account record, or package artifact
  to project evidence.

This is a conservative project gate, not legal advice and not a conclusion that
no suitable licence can exist. The specific licence has simply not been
identified here.

## Verified scope

The machine-readable decision is
[`distribution-entitlement.json`](distribution-entitlement.json). Its fingerprint
covers every tracked file whose name starts with `MinionPro-` or `MyriadPro-` in
`pdf/fonts/`. Any change to those 94 files makes the preflight fail closed.

| Operation | Environment | Recipient | Decision |
|---|---|---|---|
| Package artifact | Owner workstation | Owner | Not verified |
| Consumer canary | Consumer-owned environment | Named consumer | Not verified |
| CI build | Shared CI | CI operators | Not verified |
| Private release | Release runner | Private-registry users | Not verified |
| Public release | Release runner | Public | Prohibited by the documented personal-use scope |
| Source transfer | External workstation | External recipient | Not verified |

The generic labels above identify prohibited proposals; they do not represent a
named party or confer authorization. A future approval must add the exact,
bounded identifiers for the real environment and recipient.

## Why Adobe's public guidance is not entitlement evidence

Adobe's current [font-licensing guidance](https://helpx.adobe.com/fonts/using/font-licensing.html)
says that fonts installed in a computer's Fonts folder are governed by their own
end-user agreements. It also says Adobe Fonts service licensing does not cover
server installation or embedding fonts in desktop/mobile applications.

Adobe's [font-packaging guidance](https://helpx.adobe.com/fonts/using/package-font-files.html)
says most standard Adobe Type Library and Font Folio agreements do not permit
sending font files to third parties unless those parties have a valid licence
for the same fonts. It also emphasizes that terms vary and the specific EULA
must be checked. The [Adobe Fonts service terms](https://wwwimages2.adobe.com/content/dam/cc/en/legal/servicetou/Adobe-Fonts-Product-Specific-Terms-en_US-20240618.pdf)
apply only if these files came from that service; this repository has no evidence
that identifies their acquisition channel.

Adobe's guidance distinguishes distribution of a properly protected PDF from
transfer of font software. That distinction does not authorize distributing
this font-bearing Python package, and generic PDF-embedding guidance cannot
substitute for the missing governing licence.

## Evidence needed for a future approval

Separate explicit approval must verify all of the following before changing an
entry to `authorized`:

1. The governing licence and acquisition channel for both Adobe families.
2. The licence holder and permitted users/devices or server scope.
3. The exact build environment and operation the licence covers.
4. The exact recipient and evidence of any matching recipient licence.
5. Permission for application/package embedding and font-file transfer, not only
   permission to create or distribute rendered PDFs.
6. An approver, review date, and expiry/revalidation date.

Store only opaque references such as `CONTRACT:record-id`,
`IDENTITY:approver-id`, `ENV:record-id`, and `RECIPIENT:record-id` in the JSON
record. Keep contracts, receipts, account data, and licence files in their
authorized system; never commit, upload, or attach them here.

## Preflight

The preflight is read-only. It validates the entire record, recomputes the font
inventory, requires one exact tuple, and refuses malformed, duplicate, stale,
unknown, unverified, or prohibited state. It does not build, copy, delete, or
upload anything.

```bash
MD2PDF_OPERATION=package_artifact \
MD2PDF_ENVIRONMENT=owner_workstation \
MD2PDF_RECIPIENT=owner \
make distribution-preflight
```

That command currently exits non-zero by design. Validation failures and denials
produce a sanitized diagnostic on stderr. A future successful decision prints
JSON on stdout containing the exact tuple, proprietary inventory fingerprint,
and immutable Git tree it verified.

A successful manual run is not a durable authorization token and never
authorizes mutable worktree bytes. The final record, font fingerprint, and
decision are all read back from the immutable Git tree named in stdout. Any
future build, canary, or release workflow must consume exactly that Git tree in
an isolated checkout; it must not build from the caller's worktree, even if the
worktree was clean when preflight inspected it.

## Consumer-owned checks and ephemeral artifacts

Where transfer is not permitted, do not send this repository, a package, or font
files to a consumer. A canary may run only inside a consumer-owned environment
that already holds the source and fonts under separately verified rights. The
preflight record must name that environment and recipient exactly.

If a future approval permits a local artifact, create it only in a newly created
temporary directory, keep it on that authorized environment, prohibit uploads
and attachments, and remove that exact temporary directory when the check ends.
Do not reuse a shared output directory. These handling rules do not themselves
grant permission to create the artifact.
