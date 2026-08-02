# Visual PDF acceptance evidence

This directory holds the small, reviewable evidence for the table-width PDF
acceptance matrix. Full PDFs and full-size page rasterizations are generated
under the ignored `output/pdf/visual-acceptance/candidates/` tree. Only an
explicitly reviewed candidate's manifest and contact sheets are promoted here.

The fixture is wholly synthetic. It covers ladders, schedules, summaries,
prose and long-token wrapping, declared layouts, the legacy opt-out, portrait
and landscape stress cases, and every bundled theme (`alpine`, `wnc`,
`regrading`, `neutral`, and `compact`).

## Canonical environment

The first approved evidence was rendered on macOS arm64 with Python 3.13.13,
WeasyPrint 68.1, Markdown 3.10.3, pymdown-extensions 11.0.1, PyYAML 6.0.3,
fontTools 4.63.0, Pillow, pypdf, and Poppler 26.07.0. The authoritative manifest
records the complete platform string, direct dependency versions, raster
settings, source input hashes, and per-artifact hashes.

Raster hashes are canonical-environment evidence. Geometry, tagged-PDF
structure, semantic reading order, and content checks are intended to remain
portable across supported environments.

## Generate and verify

From the repository root, using the supported Python environment:

```sh
make visual-acceptance
python tools/visual_acceptance.py verify \
  output/pdf/visual-acceptance/candidates/<candidate-id>
```

Generation creates a new candidate; it never replaces approved evidence. A
candidate is accepted by automation only when every case renders, every table
and cell remains within the page, expected shared widths and declared
proportions hold, wrapping sentinels have the expected line counts, physical
orientation is correct, the PDF has table tags and a tagged caption, and
independent text extraction preserves the expected order. Before Poppler sees
a candidate PDF, the tool copies it from one no-follow descriptor, rejects
active or embedded objects in its decoded object graph, and requires its
canonical graph and page boxes to match an independent fresh render. Poppler
then rasterizes both private copies at 144 DPI and the tool verifies and hashes
the complete artifact set without modifying reviewed candidate files. Current
evidence uses manifest schema 3; active schema-1 and schema-2 evidence is read
only through the bounded migration validator.

## Human review

Contact sheets are navigation aids, not the approval surface. Inspect every
full-size `cases/<case-id>/page-*.png`, and inspect the corresponding PDF at
100% and 200%, before promotion. Check:

- no clipping, overlap, broken glyphs, page overflow, or lost content;
- intended one-line and wrapped cells, including the long-token sentinel;
- stable column boundaries, numeric alignment, and sibling-table widths;
- all five themes for unexpected typography, spacing, border, or colour drift;
- declared-layout and legacy output remain visibly distinct from automatic
  sizing;
- portrait stress wrapping remains inside its cells and the matching landscape
  case is materially more readable;
- captions, headings, table order, and page transitions remain coherent;
- semantic colour states remain understandable from their text, symbol, or
  weight cues when colour is unavailable, and normal/large text meets the
  WCAG 2.2 AA 4.5:1/3:1 contrast thresholds.

Record any rejection outside the candidate tree before pruning it. Do not
promote from contact-sheet inspection alone.

## Promote and resolve active evidence

After completing the checklist:

```sh
python tools/visual_acceptance.py promote \
  output/pdf/visual-acceptance/candidates/<candidate-id>
```

Promotion revalidates the candidate and its hashes, copies only the approved
manifest and contact sheets into an immutable source-digest directory under
`approved/`, then atomically updates `active.json`. Consumers must resolve the
version named by `active.json` and verify the listed hashes; they must not infer
the active version by sorting directories.

Generated candidates are disposable. Preview or apply safe retention with:

```sh
python tools/visual_acceptance.py prune --dry-run
python tools/visual_acceptance.py prune --apply
```

`make clean` also applies the contained candidate pruning policy. It does not
remove approved evidence.
